import os
import time
import json
import pandas as pd
from confluent_kafka import Consumer, KafkaError, KafkaException
import pickle
import mysql.connector
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
TOPIC_MERGE = os.getenv('TOPIC_MERGE', 'default_topic')
GROUP_ID = os.getenv('KAFKA_CONSUMER_GROUP_ID', 'my-model-consumer-group')
MODEL_PATH = os.getenv('MODEL_PATH', 'model.pkl') 

MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_USER = os.getenv('MYSQL_USER', 'user')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'password')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'database')
MYSQL_TABLE_NAME = "predictions" 

model = None
expected_features = None

try:
    logger.info(f"Intentando cargar el modelo desde '{MODEL_PATH}' usando pickle...")
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    logger.info(f"Modelo '{MODEL_PATH}' cargado exitosamente. Tipo de modelo: {type(model)}")

    if hasattr(model, 'feature_names_in_'):
        expected_features = model.feature_names_in_
        logger.info(f"Features esperadas por el modelo (según feature_names_in_): {expected_features.tolist()}")
    elif hasattr(model, 'feature_names'):
        if model.feature_names is not None:
            expected_features = model.feature_names
            logger.info(f"Features esperadas por el modelo (según Booster.feature_names): {expected_features}")

except FileNotFoundError:
    logger.error(f"Error al cargar el modelo: Archivo no encontrado en '{MODEL_PATH}'")
    model = None
except pickle.UnpicklingError as upe:
    logger.error(f"Error al des-serializar (unpickle) el modelo desde '{MODEL_PATH}': {upe}")
    model = None
except Exception as e:
    logger.error(f"Error general al cargar el modelo desde '{MODEL_PATH}': {e}")
    model = None

def get_mysql_connection():
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        logger.info(f"Conectado a MySQL en {MYSQL_HOST}:{MYSQL_PORT}, DB: {MYSQL_DATABASE}")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Error al conectar con MySQL: {err}")
        return None

def create_predictions_table_if_not_exists(conn):
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {MYSQL_TABLE_NAME} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                country VARCHAR(255),
                region VARCHAR(255),
                score_real FLOAT,
                score_predict FLOAT
            )
        """)
        conn.commit()
        logger.info(f"Tabla '{MYSQL_TABLE_NAME}' verificada/creada en MySQL con nuevas columnas.")
    except mysql.connector.Error as err:
        logger.error(f"Error al crear/verificar la tabla de predicciones: {err}")

def save_prediction_to_mysql(conn, country, region, score_real, score_predict_raw):
    if not conn:
        logger.error("No hay conexión a MySQL para guardar la predicción.")
        return
    
    processed_score_predict = None
    if hasattr(score_predict_raw, '__iter__') and not isinstance(score_predict_raw, (str, bytes)):
        if len(score_predict_raw) > 0:
            processed_score_predict = float(score_predict_raw[0]) 
    elif isinstance(score_predict_raw, (int, float)):
        processed_score_predict = float(score_predict_raw)
    else:
        logger.warning(f"Formato de score_predict no esperado: {score_predict_raw}. No se pudo extraer un float.")

    sql = f"INSERT INTO {MYSQL_TABLE_NAME} (country, region, score_real, score_predict) VALUES (%s, %s, %s, %s)"
    val = (country, region, score_real, processed_score_predict)
    
    try:
        cursor = conn.cursor()
        cursor.execute(sql, val)
        conn.commit()
        logger.info(f"Predicción guardada en MySQL para {country}. ID: {cursor.lastrowid}")
    except mysql.connector.Error as err:
        logger.error(f"Error al guardar predicción en MySQL: {err}")
    except Exception as e:
        logger.error(f"Error inesperado al guardar en MySQL: {e}")

def get_region_from_message(message_data):
    for key, value in message_data.items():
        if key.startswith("region_") and value is True:
            return key.replace("region_", "").replace(" and ", " and ") 
    return None

def main():
    global expected_features
    logger.info("Iniciando consumidor de modelo...")
    logger.info(f"Servidores Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Topic: {TOPIC_MERGE}, Grupo: {GROUP_ID}")

    if model is None:
        logger.error("El modelo no se cargó. El consumidor no puede continuar.")
        return

    consumer_config = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': GROUP_ID,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False
    }
    consumer = Consumer(consumer_config)
    consumer.subscribe([TOPIC_MERGE])

    db_conn = get_mysql_connection()
    if db_conn:
        create_predictions_table_if_not_exists(db_conn)
    else:
        logger.error("No se pudo establecer conexión con MySQL. Las predicciones no se guardarán.")

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.info('%% %s [%d] llegó al final del offset %d\n' %
                                  (msg.topic(), msg.partition(), msg.offset()))
                elif msg.error():
                    raise KafkaException(msg.error())
            else:
                try:
                    message_data = json.loads(msg.value().decode('utf-8'))
                    logger.info(f"Mensaje recibido de Kafka (primeras ~100 chars): {str(message_data)[:100]}...")

                    input_df_raw = pd.DataFrame([message_data])
                    
                    features_for_prediction_df = input_df_raw.drop(columns=['country', 'score'], errors='ignore')
                    
                    if expected_features is not None:
                        try:
                            missing_features = set(expected_features) - set(features_for_prediction_df.columns)
                            if missing_features:
                                logger.error(f"Faltan features en los datos de entrada después del drop: {missing_features}. Features esperadas: {expected_features}")
                                consumer.commit(asynchronous=False)
                                continue
                            features_for_prediction_df = features_for_prediction_df[expected_features]
                        except KeyError as ke:
                            logger.error(f"Error al reordenar/seleccionar columnas basado en expected_features: {ke}")
                            consumer.commit(asynchronous=False)
                            continue
                    else:
                        logger.warning("No se pudieron determinar las 'expected_features' del modelo. Usando todas las columnas restantes después de drop.")
                    
                    prediction_output = None
                    try:
                        if hasattr(model, 'predict'):
                            prediction_output = model.predict(features_for_prediction_df)
                            logger.info(f"Predicción del modelo: {prediction_output}")
                        else:
                            logger.error(f"El objeto modelo (tipo: {type(model)}) no tiene un método 'predict' estándar.")
                            consumer.commit(asynchronous=False)
                            continue
                    except Exception as e_predict:
                        logger.error(f"Error durante la predicción: {e_predict}")
                        logger.error(f"Datos de entrada para predicción: {features_for_prediction_df.to_dict()}")
                        consumer.commit(asynchronous=False)
                        continue
                    
                    country_val = message_data.get('country')
                    score_real_val = message_data.get('score')
                    region_val = get_region_from_message(message_data)

                    if db_conn and db_conn.is_connected():
                        save_prediction_to_mysql(db_conn, country_val, region_val, score_real_val, prediction_output)
                    elif db_conn is None or not db_conn.is_connected():
                        logger.warning("Intentando reconectar a MySQL...")
                        db_conn = get_mysql_connection()
                        if db_conn and db_conn.is_connected():
                             create_predictions_table_if_not_exists(db_conn)
                             save_prediction_to_mysql(db_conn, country_val, region_val, score_real_val, prediction_output)
                        else:
                            logger.error("Reconexión a MySQL fallida. Predicción no guardada.")
                    
                    consumer.commit(asynchronous=False)

                except json.JSONDecodeError:
                    logger.error(f"Error al decodificar JSON del mensaje: {msg.value()}")
                    consumer.commit(asynchronous=False)
                except Exception as e:
                    logger.error(f"Error general al procesar el mensaje: {e}")
                    consumer.commit(asynchronous=False) 

    except KeyboardInterrupt:
        logger.info("Consumidor interrumpido. Cerrando...")
    finally:
        consumer.close()
        if db_conn and db_conn.is_connected():
            db_conn.close()
            logger.info("Conexión a MySQL cerrada.")
        logger.info("Consumidor finalizado.")

if __name__ == '__main__':
    time.sleep(15) 
    main()
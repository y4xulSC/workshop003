import os
import time
import pandas as pd
from confluent_kafka import Producer
import json
import logging

import sys

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
TOPIC_MERGE = os.getenv('TOPIC_MERGE', 'default_topic')
CSV_FILE_PATH = os.getenv('CSV_FILE', '/data.csv')

def delivery_report(err, msg):
    """ Callback para el resultado de la producción de mensajes. """
    if err is not None:
        logger.error(f'Error al entregar mensaje: {err}')
    else:
        logger.info(f'Mensaje entregado a {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}')

def main():
    logger.info("Iniciando productor de datos...")
    logger.info(f"Servidores Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Topic: {TOPIC_MERGE}")
    logger.info(f"Archivo CSV: {CSV_FILE_PATH}")

    producer_config = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS
    }
    producer = Producer(producer_config)

    try:
        df = pd.read_csv(CSV_FILE_PATH)
        logger.info(f"Archivo CSV '{CSV_FILE_PATH}' cargado. Número de filas: {len(df)}")
    except FileNotFoundError:
        logger.error(f"Error: No se encontró el archivo CSV en '{CSV_FILE_PATH}'")
        return
    except Exception as e:
        logger.error(f"Error al leer el archivo CSV: {e}")
        return

    for index, row in df.iterrows():
        message = row.to_dict()
        try:
            producer.produce(
                TOPIC_MERGE,
                key=str(index),
                value=json.dumps(message).encode('utf-8'),
                callback=delivery_report
            )
            producer.poll(0) 

        except BufferError:
            logger.warning(f'Buffer de productor lleno. Esperando... (mensaje {index})')
            producer.poll(1)
            producer.produce(
                TOPIC_MERGE,
                key=str(index),
                value=json.dumps(message).encode('utf-8'),
                callback=delivery_report
            )
        except Exception as e:
            logger.error(f"Error al producir mensaje para fila {index}: {e}")

    logger.info("Esperando a que todos los mensajes sean entregados...")
    producer.flush()
    logger.info("Todos los mensajes han sido enviados.")

if __name__ == '__main__':
    time.sleep(10) 
    main()
    logger.info("Productor finalizado.")
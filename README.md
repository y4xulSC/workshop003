# World Happiness Index Prediction Pipeline

This project aims to predict the happiness index of various countries using historical data from the World Happiness Report (2015-2019). The pipeline includes data processing, training an XGBoost regression model, and deploying a Kafka-based producer-consumer system using Docker to make real-time predictions and store them in a MySQL database.

## Project Structure

| **Path**                                   | **Description**                                                                 |
|--------------------------------------------|---------------------------------------------------------------------------------|
| `assets/docs/guide.pdf`                    | Project guide document.                                                         |
| `data/processed/score_merge.csv`           | Merged and cleaned data (pre-OHE).                                              |
| `data/processed/score_merge_ohe.csv`       | Merged data with one-hot encoding (input for training).                         |
| `data/processed/test_data.csv`             | Test data subset for the producer (ensure this exists).                         |
| `data/raw/2015.csv`                        | Raw data for the year 2015.                                                    |
| `data/raw/2016.csv`                        | Raw data for the year 2016.                                                    |
| `data/raw/2017.csv`                        | Raw data for the year 2017.                                                    |
| `data/raw/2018.csv`                        | Raw data for the year 2018.                                                    |
| `data/raw/2019.csv`                        | Raw data for the year 2019.                                                    |
| `docker/docker-compose.yml`                | Docker Compose file to orchestrate services.                                    |
| `docker/Dockerfile.consumer`               | Dockerfile for the model consumer service.                                      |
| `docker/Dockerfile.producer`               | Dockerfile for the data producer service.                                       |
| `docker/.env`                              | Local environment configuration (needs to be created by user).                  |
| `model/GXBoost.pkl`                        | Trained XGBoost model (ensure this exists).                                     |
| `mysql-init/init.sh`                       | MySQL database initialization script.                                           |
| `notebooks/EDA_TRANSFORM.ipynb`            | Jupyter notebook for EDA and data transformation.                               |
| `notebooks/TRAIN.ipynb`                    | Jupyter notebook for model training and test data generation.                   |
| `README.md`                                | Project README file.                                                           |
| `requirements.txt`                         | Python dependencies for the project.                                           |
| `src/consumer/main.py`                     | Main script for the Kafka consumer & model prediction.                          |
| `src/producer/main.py`                     | Main script for the Kafka producer.                                             |

## Core Components

*   **`notebooks/EDA_TRANSFORM.ipynb`**:
    *   Loads raw happiness data (2015-2019).
    *   Performs Exploratory Data Analysis (EDA).
    *   Cleans, standardizes column names, imputes missing values (e.g., `region`), and merges datasets.
    *   Applies One-Hot Encoding to categorical features (`region`, `year`).
    *   Outputs `data/processed/score_merge_ohe.csv` for training.
*   **`notebooks/TRAIN.ipynb`**:
    *   Loads `data/processed/score_merge_ohe.csv`.
    *   Splits data into training and test sets.
    *   Trains multiple regression models and selects XGBoost as the best performer based on R² score.
    *   Saves the trained XGBoost model (e.g., as `model/XGBoost.pkl`).
    *   Saves the test data subset (e.g., as `data/processed/test_data_for_prediction.csv`) for the producer.
*   **`src/producer/main.py`**:
    *   Reads data row by row from a CSV file (e.g., `data/processed/test_data.csv`, mounted into the container).
    *   Publishes each row as a JSON message to the `merge_topic` Kafka topic.
*   **`src/consumer/main.py`**:
    *   Loads the pre-trained XGBoost model (e.g., `model/GXBoost.pkl`, mounted into the container).
    *   Consumes messages from the `merge_topic` Kafka topic.
    *   For each message, performs a happiness score prediction using the loaded model.
    *   Stores the original data (country, region, actual score) along with the predicted score into the `predictions` table in a MySQL database.
*   **`mysql-init/init.sh`**:
    *   An initialization script executed on MySQL container startup. It creates the specified database and user with necessary privileges, using credentials from the `.env` file.

## Technologies Used

*   Python
*   Pandas & NumPy (for data manipulation)
*   Scikit-learn (for model evaluation and utilities)
*   XGBoost (for the prediction model)
*   Confluent Kafka (for message queuing)
*   MySQL (for storing predictions)
*   Docker & Docker Compose (for containerization and orchestration)
*   Jupyter Notebooks (for EDA and model training)

## Prerequisites

*   Docker installed and running.
*   Docker Compose installed.

## Setup and Running the Pipeline

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/y4xulSC/workshop3
    cd workshop3
    ```

2.  **Generate Model and Test Data:**
    *   Run the Jupyter Notebooks in order:
        1.  `notebooks/EDA_TRANSFORM.ipynb` (to create `data/processed/score_merge_ohe.csv`)
        2.  `notebooks/TRAIN.ipynb` (to create the model file and the test data CSV)
    *   **Important - File Naming:**
        *   The `TRAIN.ipynb` (as per recent changes) saves the model as `model/XGBoost.pkl`. The Docker setup (e.g., `Dockerfile.consumer`, `docker/.env`) expects `model/GXBoost.pkl`. **Rename or copy `model/XGBoost.pkl` to `model/GXBoost.pkl`**.
        *   The `TRAIN.ipynb` saves test data as `data/processed/test_data_for_prediction.csv`. The Docker setup expects `data/processed/test_data.csv` (as per `docker/.env`). **Rename or copy `data/processed/test_data_for_prediction.csv` to `data/processed/test_data.csv`**.

3.  **Create Environment File:**
    The `docker-compose.yml` file (located in `docker/`) uses an `env_file` directive that expects a `.env` file in the *same directory*. Create `docker/.env` with the following content:
    ```env
    # MySQL Credentials (used by mysql service and init.sh)
    MYSQL_ROOT_PASSWORD=
    MYSQL_DATABASE=
    MYSQL_USER=
    MYSQL_PASSWORD=
    # Kafka Configuration (used by producer and consumer scripts)
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    TOPIC_MERGE=merge_topic

    # Path for the producer's input CSV (inside the producer container)
    CSV_FILE=/app/data_to_process/test_data.csv

    # Path for the consumer's model file (inside the consumer container)
    MODEL_PATH=/app/GXBoost.pkl
    ```

4.  **Build and Run with Docker Compose:**
    From the project's **root directory**:
    ```bash
    docker-compose -f docker/docker-compose.yml up --build -d
    ```
    This command builds the images for the producer and consumer (if not already built or if Dockerfiles changed) and starts all services defined in `docker-compose.yml` in detached mode.

5.  **Verify Operation:**
    *   The `data_producer` service will read `test_data.csv` and send messages to Kafka.
    *   The `model_consumer` service will process these messages, make predictions, and store them in the `predictions` table in the `happy` MySQL database.
    *   Check logs: `docker-compose -f docker/docker-compose.yml logs <service_name>` (e.g., `data_producer`, `model_consumer`, `mysql`).

6.  **Accessing MySQL Data (Optional):**
    The MySQL server is exposed on port `3307` of your host machine. Connect using a MySQL client:
    *   Host: `localhost` (or `127.0.0.1`)
    *   Port: `3307`
    *   User: `user` (from `.env`)
    *   Password: `your_password` (from `.env`)
    *   Database: `your_database` (from `.env`)
    Query the `predictions` table: `SELECT * FROM predictions;`

7.  **Stopping the Pipeline:**
    From the project's **root directory**:
    ```bash
    docker-compose -f docker/docker-compose.yml down
    ```
    This stops and removes the containers. Add `-v` to also remove volumes (like `mysql_data`) if desired.
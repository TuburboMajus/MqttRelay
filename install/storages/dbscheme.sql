/******************************\
 *  INITIALIZE
\******************************/ 

drop database IF EXISTS $database;
create database $database;
use $database;


/******************************\
 * APP
\******************************/

create table mqtt_relay(
    version varchar(20) primary key not null
);

/******************************\
 * TABLES
\******************************/
CREATE TABLE IF NOT EXISTS mqtt_messages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    topic VARCHAR(255) NOT NULL,
    payload_json JSON NULL,
    payload_text TEXT NULL,
    qos TINYINT UNSIGNED NOT NULL DEFAULT 0,
    retain TINYINT(1) NOT NULL DEFAULT 0,
    received_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_topic_received (topic, received_at),
    INDEX idx_received (received_at)
);
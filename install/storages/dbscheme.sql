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
    client VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    payload TEXT NULL,
    qos TINYINT UNSIGNED NOT NULL DEFAULT 0,
    at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_topic_received (topic, at),
    INDEX idx_received (at)
);
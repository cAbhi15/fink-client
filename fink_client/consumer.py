#!/usr/bin/env python
# Copyright 2019 AstroLab Software
# Author: Abhishek Chauhan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import io
import os
import json
import confluent_kafka
import fastavro
import requests
from confluent_kafka import KafkaError
from requests.exceptions import RequestException
from typing import Any

class AlertError(Exception):
    pass


class AlertConsumer:
    """
    High level Kafka consumer to receive alerts from Fink broker
    """

    def __init__(self, topics: list, config: dict, schema=None):
        """Creates an instance of `AlertConsumer`

        Parameters
        ----------
        topics : list of str
            list of topics to subscribe
        config: dict
            Dictionary of configurations

            username: str
                username for API access
            password: str
                password for API access
            group_id: str
                group.id for Kafka consumer
            bootstrap.servers: str, optional
                Kafka servers to connect to
        """
        self._topics = topics
        self._kafka_config = _get_kafka_config(config)
        self._parsed_schema = _get_alert_schema(schema_path=schema)
        self._consumer = confluent_kafka.Consumer(self._kafka_config)
        self._consumer.subscribe(self._topics)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self._consumer.close()

    def poll(self, timeout: float = -1) -> (str, dict):
        """Consume messages from Fink server

        Parameters
        ----------
        timeout: float
            maximum time to block waiting for a message
            if not set default is None i.e. wait indefinitely

        Returns
        ----------
        (topic, alert): tuple(str, dict)
            returns (None, None) on timeout
        """
        msg = self._consumer.poll(timeout)
        if msg is None:
            return None, None

        # msg.error() returns None or KafkaError
        if msg.error():
            error_message = ("Error: {}\n"
                "topic: {}[{}] at offset: {} with key: {}").format(
                msg.error, msg.topic(), msg.partition(), msg.offset(),
                str(msg.key))
            raise AlertError(error_message)

        topic = msg.topic()
        avro_alert = io.BytesIO(msg.value())
        alert = _decode_avro_alert(avro_alert, self._parsed_schema)

        return topic, alert

    def consume(self, num_alerts: int = 1, timeout: float = -1) -> list:
        """Consume and return list of messages

        Parameters
        ----------
        num_messages: int
            maximum number of messages to return

        timeout: float
            maximum time to block waiting for messages
            if not set default is None i.e. wait indefinitely

        Returns
        ----------
        list: [tuple(str, dict)]
            list of topic, alert
            returns an empty list on timeout
        """
        alerts = []
        msg_list = self._consumer.consume(num_alerts, timeout)

        for msg in msg_list:
            topic = msg.topic()
            avro_alert = io.BytesIO(msg.value())
            alert = _decode_avro_alert(avro_alert, self._parsed_schema)

            alerts.append((topic, alert))

        return alerts

    def close(self):
        """Close connection to Fink broker"""
        self._consumer.close()


def _get_kafka_config(config: dict) -> dict:
    """Returns configurations for a consumer instance

    Parameters
    ----------
    config: dict
        Dictionary of configurations

    Returns
    ----------
    kafka_config: dict
        Dictionary with configurations for creating an instance of
        a secured Kafka consumer
    """
    kafka_config = {}
    default_config = {
        "auto.offset.reset": "earliest"
    }

    if 'username' in config and 'password' in config:
        kafka_config["security.protocol"] = "sasl_plaintext"
        kafka_config["sasl.mechanism"] = "SCRAM-SHA-512"
        kafka_config["sasl.username"] = config["username"]
        kafka_config["sasl.password"] = config["password"]

    kafka_config["group.id"] = config["group_id"]

    kafka_config.update(default_config)

    # use servers if given
    if 'bootstrap.servers' in config:
        kafka_config["bootstrap.servers"] = config["bootstrap.servers"]
    else:
        # use default fink_servers
        fink_servers = [
                "localhost:9093",
                "localhost:9094",
                "localhost:9095"
        ]
        kafka_config["bootstrap.servers"] = "{}".format(",".join(fink_servers))

    return kafka_config


def _get_alert_schema(schema_path: str = None):
    """Returns schema for decoding avro alert

    This method downloads the latest schema available on the fink servers
    or falls back to using a default schema located in dir 'schemas'/

    Parameters
    ----------
    schema_path: str, optional
        a local path where to look for schema,
        Note that schema doesn't get downloaded from fink servers if schema_path
        is given

    Returns
    ----------
    parsed_schema: dict
        Dictionary of json format schema for decoding avro alerts from fink
    """
    if schema_path is None:
        # get schema from fink-broker
        try:
            print("Getting schema from fink servers...")
            schema_url = "https://raw.github.com/astrolabsoftware/fink-broker/master/schemas/distribution_schema.avsc"
            filename = schema_url.split("/")[-1]
            r = requests.get(schema_url, timeout=1)
            schema_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '../schemas/{}'.format(filename)))
            with open(schema_path, "w") as f:
                f.write(r.text)
        except RequestException:
            schema_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '../schemas/fink_alert_schema.avsc'))
            m = ("Could not obtain schema from fink servers\n"
                "Using default schema available at: {}").format(schema_path)
            print(m)

    with open(schema_path) as f:
        schema = json.load(f)

    return fastavro.parse_schema(schema)


def _decode_avro_alert(avro_alert: io.IOBase, schema: dict) -> Any:
    """Decodes a file-like stream of avro data

    Parameters
    ----------
    avro_alert: io.IOBase
        a file-like stream with avro encoded data

    schema: dict
        Dictionary of json format schema to decode avro data

    Returns
    ----------
    record: Any
        Record obtained after decoding avro data (typically, dict)
    """
    avro_alert.seek(0)
    return fastavro.schemaless_reader(avro_alert, schema)

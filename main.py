#!/usr/bin/env python3
"""
Canary to MQTT Data Forwarder
Reads live data from Canary and forwards it to MQTT broker.
"""

import gc
import logging
import os
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, List

import paho.mqtt.client as mqtt
from birdsong import CanaryView
from dotenv import load_dotenv

load_dotenv()


def setup_logging():
    """Setup logging with both console and rotating file handlers."""
    log_dir = '/app/logs'
    os.makedirs(log_dir, exist_ok=True)

    log_level_str = os.getenv("LOGLEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "canary_forwarder.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)


logger = setup_logging()


class PathTranspose:
    """Utility class for converting between Canary and MQTT path formats."""

    @staticmethod
    def from_canary_path(path: str) -> str:
        """Convert Canary path format to MQTT topic format."""
        return path.replace(".", "/")

    @staticmethod
    def to_canary_path(path: str) -> str:
        """Convert MQTT topic format to Canary path format."""
        return path.replace("/", ".")


class MQTTForwarder:
    """Handles MQTT connection and message forwarding."""

    def __init__(self, mqtt_host: str):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_host = mqtt_host
        self._setup_callbacks()

    def _setup_callbacks(self):
        """Setup MQTT client callbacks."""
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback for when MQTT client connects."""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"Failed to connect to MQTT broker: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Callback for when MQTT client disconnects."""
        logger.info("Disconnected from MQTT broker")

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        """Callback for when message is published."""
        if reason_code != 0:
            logger.warning(f"Publish failed with reason code: {reason_code}")

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            self.client.connect(host=self.mqtt_host)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker."""
        self.client.loop_stop()
        self.client.disconnect()

    def publish_data(self, topic: str, data: Dict[str, Any]) -> bool:
        """Publish data to MQTT topic."""
        try:
            result = self.client.publish(topic=topic, payload=str(data))
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing to topic {topic}: {e}")
            return False


class CanaryDataForwarder:
    """Main class for forwarding Canary data to MQTT."""

    def __init__(self):
        self.canary_host = os.environ.get("Canary_Url")
        self.canary_dataset = os.environ.get("Canary_Dataset")
        self.mqtt_host = os.environ.get("Mqtt_Url")

        self._validate_config()

        self.mqtt_forwarder = MQTTForwarder(self.mqtt_host)
        self.tag_list: List[str] = []
        self.running = True

        self._setup_signal_handlers()

    def _validate_config(self):
        """Validate required environment variables."""
        required_vars = ["Canary_Url", "Canary_Dataset", "Mqtt_Url"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal, stopping gracefully...")
        self.running = False

    def _load_tag_list(self) -> bool:
        """Load tag list from Canary."""
        try:
            with CanaryView(host=self.canary_host) as view:
                self.tag_list = list(
                    view.browseTags(path=self.canary_dataset, deep=True)
                )
                logger.info(f"Loaded {len(self.tag_list)} tags from Canary")
                return True
        except Exception as e:
            logger.error(f"Error loading tag list: {e}")
            return False

    def _process_data_batch(self, data_dict: Dict[str, Any]) -> int:
        """Process a batch of data and forward to MQTT."""
        published_count = 0

        for key, value in data_dict.items():
            if value and len(value) > 0:
                tvq_object = value[0]

                try:
                    if hasattr(tvq_object, "value") and tvq_object.value is not None:
                        timestamp = getattr(tvq_object, "timestamp", None)
                        if timestamp and hasattr(timestamp, "isoformat"):
                            timestamp = timestamp.isoformat()

                        data_to_publish = {
                            "value": tvq_object.value,
                            "timestamp": timestamp,
                            "quality": getattr(tvq_object, "quality", None),
                        }

                        topic = PathTranspose.from_canary_path(key)
                        if self.mqtt_forwarder.publish_data(topic, data_to_publish):
                            published_count += 1
                        else:
                            logger.warning(f"Failed to publish data for tag: {key}")

                except AttributeError as e:
                    logger.debug(f"Could not access value for tag {key}: {e}")
                except Exception as e:
                    logger.warning(f"Error processing data for tag {key}: {e}")

        return published_count

    def run(self):
        """Main execution loop."""
        logger.info("Starting Canary to MQTT forwarder...")

        if not self._load_tag_list():
            logger.error("Failed to load tag list, exiting")
            return

        if not self.mqtt_forwarder.connect():
            logger.error("Failed to connect to MQTT broker, exiting")
            return

        try:
            with CanaryView(host=self.canary_host) as view:
                logger.info("Starting data forwarding loop...")

                while self.running:
                    try:
                        data = view.getLiveData(tags=self.tag_list, includeQuality=True)
                        data_dict = dict(data)
                        published_count = self._process_data_batch(data_dict)

                        if published_count > 0:
                            logger.debug(f"Published {published_count} data points")

                        del data, data_dict
                        gc.collect()

                        logger.debug(
                            f"sleeping for {str(os.getenv('WAITTIME', '1'))} seconds"
                        )
                        time.sleep(float(os.getenv("WAITTIME", "1")))

                    except Exception as e:
                        logger.error(f"Error in main loop: {e}")
                        time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            self._cleanup()

    def _cleanup(self):
        """Cleanup resources."""
        logger.info("Cleaning up resources...")
        self.mqtt_forwarder.disconnect()
        logger.info("Shutdown complete")


def main():
    """Main entry point."""
    try:
        forwarder = CanaryDataForwarder()
        forwarder.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

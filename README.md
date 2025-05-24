# simple-canary-mqtt-forwarder
A lightweight tool for forwarding data from a single Canary dataset to a single MQTT broker.

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/huntermatuse/simple-canary-mqtt-forwarder.git
cd simple-canary-mqtt-forwarder
```

### 2. Configure Environment Variables

Copy the example environment file and update it with your configuration:

```bash
cp .env.example .env
```

Then, open `.env` and fill in your specific settings:

```env
Canary_Url=''        # URL to your Canary Historian
Canary_Dataset=''    # Name of the Canary dataset to forward
Mqtt_Url=''          # MQTT broker URL
# TIMEZONE='UTC'     # Not currently functional
WAITTIME=0.5         # Time in seconds between data polls
LOGLEVEL='NOTSET'    # Logging level (e.g., DEBUG, INFO, WARNING)
```

### 3. Run the Application

The quickest way to start the forwarder is using Docker:

```bash
docker compose up -d
```

## Notes

* This tool currently supports forwarding from **one** Canary dataset to **one** MQTT broker.
* The `TIMEZONE` option is present but not yet supported.
* Set `WAITTIME` appropriately based on your desired polling interval.

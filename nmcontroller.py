# -*- coding: utf-8 -*-
"""
@file: nmcontroller.py
@author: NM
@copyright  Copyright (c) 2024, NMTech. All rights reserved

This script initializes and runs the NMMiner monitoring server using Flask.
It listens for miner updates via UDP and retrieves Bitcoin block reward and price information.
"""

import os
import socket
import sys
import time
import logging

import waitress
from flask import Flask, render_template

from threads.btcinfo_thread import BtcInfoThread
from threads.udp_thread import UdpThread
from utils import hashrate_formatter, firmware_utils
from utils.time_format_utils import split_time_string, compact_uptime, time_difference

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Set up template folder for Flask (for PyInstaller compatibility)
if hasattr(sys, '_MEIPASS'):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
else:
    template_folder = 'templates'

app = Flask(__name__, template_folder=template_folder)
hasher = hashrate_formatter.HashrateFormatter()


@app.route('/', methods=['GET', 'POST'])
@app.route('/web_monitor', methods=['GET', 'POST'])
def web_monitor():
    """
    Web route for the monitoring page.

    Retrieves miner data, processes statistics, and renders the web interface.

    :return: Rendered HTML template with miner details and Bitcoin stats.
    """
    nmminer_list = []
    total_hashrate = 0.0

    # Retrieve miner map and iterate through sorted miners
    for miner_id, miner_data in sorted(udp_thread.get_miner_map().items()):
        version = miner_data.get('Version', 'Unknown')

        # Check if firmware version is outdated
        if not firmware_utils.compare_versions(version, latest_version):
            version += '*'

        upTime, _ = split_time_string(miner_data.get('Uptime', '0'))

        rejected, accepted, percentage = miner_data.get("Share", 0).split('/')

        # Append relevant miner details
        nmminer_list.append([
            miner_data.get('ip', 'Unknown'),
            miner_data.get("BoardType", 'Unknown'),
            miner_data.get('HashRate', '0'),
            f'{rejected}/{accepted} ({percentage})',
            miner_data.get('NetDiff', 0),
            miner_data.get('BestDiff', 0),
            miner_data.get('Valid', 0),
            round(miner_data.get('Temp', 0.0), 1),
            miner_data.get('RSSI', 0),
            round(miner_data.get('FreeHeap', 0.0), 2),
            version,
            compact_uptime(upTime),
            time_difference(miner_data.get('UpdateTime', 'Unknown')),
            miner_data.get('LastDiff', 0),
        ])

        # Convert and accumulate hashrate
        hashrate_value = miner_data.get('HashRate')
        if hashrate_value:
            total_hashrate += hasher.convert_hashrate(hashrate_value)

    # Render template with miner statistics
    return render_template(
        'web_monitor.html',
        result=nmminer_list,
        totalHash=hasher.format_hashrate(total_hashrate),
        latest_version=latest_version,
        reward_value=btcinfo_thread.block_reward_value,
        block_reward=btcinfo_thread.block_reward,
        btc_price=btcinfo_thread.btc_price,
        btc_price_source=btcinfo_thread.btc_price_source,
    )


def get_local_ip():
    """
    Retrieve the local IP address of the machine.

    :return: Local IP address as a string.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception as e:
        logging.error(f"Failed to retrieve local IP: {e}")
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def logo_print():
    """Prints ASCII logo for the NMTech monitor."""
    print("""
            ___          ___         
           /\\__\\        /\\__\\    
          /::|  |      /::|  |       
         /:|:|  |     /:|:|  |       
        /:/|:|  |__  /:/|:|__|__     
       /:/ |:| /\\__\\/:/ |::::\\__\\
       \\/__|:|/:/  /\\/__/~~/:/  /  
           |:/:/  /       /:/  /     
           |::/  /       /:/  /      
           /:/  /       /:/  /       
           \\/__/        \\/__/      
    """)


if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 7877

    logo_print()
    logging.info("NM Centralized Monitor Server running...")
    logging.info("NMMiner firmware version v0.3.01 or later is required.")

    # Retrieve latest firmware version
    latest_version = firmware_utils.get_latest_version()
    logging.info(f"The latest version of NMMiner is {latest_version}.")

    # Start monitoring threads
    btcinfo_thread = BtcInfoThread(name="BTC_Info", update_seconds=1800)
    udp_thread = UdpThread(name="NMMiner_Info")

    time.sleep(2)  # Allow threads to initialize

    logging.info(f"Access the web monitor at http://{local_ip}:{port} or http://localhost:{port}")

    # Open browser automatically on macOS
    cwd = os.getcwd()
    if '.app/Contents/Resources' in cwd:
        logging.info("Running on macOS")
        os.system('open "http://127.0.0.1:7877"')

    try:
        # Start the Flask server with Waitress
        waitress.serve(app, host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        logging.info("Shutting down server...")

    # Ensure proper shutdown of threads
    logging.info("Stopping threads...")
    udp_thread.stop()
    btcinfo_thread.stop()

    logging.info("NM Centralized Monitor Server closed.")

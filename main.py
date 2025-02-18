from flask import Flask, request
import asyncio
from flask_cors import CORS
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import sessionmaker
from models import AutoDialerCampaign, User
from autodialer import start_autodialer_campaign, complete_autodialer_campaign
from ranablast import start_ranablast_campaign, complete_ranablast_campaign

from config import Session
from loggers import app_logger, autodialer_logger, ranablast_logger
from config_socket import sio, SOCKET_URL  # Impor SOCKET_URL juga
import pytz
from apscheduler.jobstores.base import JobLookupError
# Menyiapkan scheduler
scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Jakarta'), job_defaults={'misfire_grace_time': 60})  # Mengatur zona waktu Jakarta
scheduler.start()

app = Flask(__name__)
CORS(app)  # Mengizinkan akses lintas-origin

@sio.event
def reschedule_campaign_autodialer(data):
    campaign_id = data.get('data', {}).get('campaign_id')
    start_date_str = data.get('data', {}).get('start_date')
    end_date_str = data.get('data', {}).get('end_date')
    status = data.get('data').get('status')

   # Convert strings to datetime objects
    start_date = datetime.fromisoformat(start_date_str)
    end_date = datetime.fromisoformat(end_date_str)
    now = datetime.now()

    # Validate dates
    if start_date < now:
        autodialer_logger.error(f"Start date {start_date} for campaign {campaign_id} is in the past. Skipping scheduling.")
        return
    if end_date <= start_date:
        autodialer_logger.error(f"End date {end_date} for campaign {campaign_id} must be after start date {start_date}.")
        return

    start_job_id = f"campaign_start_autodialer_{campaign_id}"
    end_job_id = f"campaign_end_autodialer_{campaign_id}"

      # Remove existing jobs if they exist
    try:
        scheduler.remove_job(start_job_id)
    except JobLookupError:
        pass  # Job might not exist yet, which is fine
    try:
        scheduler.remove_job(end_job_id)
    except JobLookupError:
        pass  # Job might not exist yet, which is fine

    # Schedule new start job if the campaign is active
    if status == "Active":
        scheduler.add_job(
            start_autodialer_campaign,
            "date",
            run_date=start_date,
            args=[campaign_id],
            id=start_job_id,
            name=f"Start Autodial Campaign {campaign_id}",
        )
        autodialer_logger.info(f"Scheduled campaign {campaign_id} to start at {start_date}")

    # Schedule end job to mark the campaign as completed
    if status != "Completed":
        scheduler.add_job(
            complete_autodialer_campaign,
            "date",
            run_date=end_date,
            args=[campaign_id],
            id=end_job_id,
            name=f"Complete Autodial Campaign {campaign_id}",
        )
        autodialer_logger.info(f"Scheduled campaign {campaign_id} to end at {end_date}")

@sio.event
def reschedule_campaign_ranablast(data):
    campaign_id = data.get('data', {}).get('campaign_id')
    start_date_str = data.get('data', {}).get('start_date')
    end_date_str = data.get('data', {}).get('end_date')
    status = data.get('data').get('status')

   # Convert strings to datetime objects
    start_date = datetime.fromisoformat(start_date_str)
    end_date = datetime.fromisoformat(end_date_str)
    now = datetime.now()

    # Validate dates
    if start_date < now:
        ranablast_logger.error(f"Start date {start_date} for campaign {campaign_id} is in the past. Skipping scheduling.")
        return
    if end_date <= start_date:
        ranablast_logger.error(f"End date {end_date} for campaign {campaign_id} must be after start date {start_date}.")
        return

    start_job_id = f"campaign_start_ranablast_{campaign_id}"
    end_job_id = f"campaign_end_ranablast_{campaign_id}"

      # Remove existing jobs if they exist
    try:
        scheduler.remove_job(start_job_id)
    except JobLookupError:
        pass  # Job might not exist yet, which is fine
    try:
        scheduler.remove_job(end_job_id)
    except JobLookupError:
        pass  # Job might not exist yet, which is fine

    # Schedule new start job if the campaign is active
    if status == "Active":
        scheduler.add_job(
            start_ranablast_campaign,
            "date",
            run_date=start_date,
            args=[campaign_id],
            id=start_job_id,
            name=f"Start Ranablast Campaign {campaign_id}",
        )
        ranablast_logger.info(f"Scheduled campaign {campaign_id} to start at {start_date}")

    # Schedule end job to mark the campaign as completed
    if status != "Selesai":
        scheduler.add_job(
            complete_ranablast_campaign,
            "date",
            run_date=end_date,
            args=[campaign_id],
            id=end_job_id,
            name=f"Complete Ranablast Campaign {campaign_id}",
        )
        ranablast_logger.info(f"Scheduled campaign {campaign_id} to end at {end_date}")

def connect_socket():
    """
    Fungsi untuk memastikan koneksi dengan server Socket.IO.
    """
    try:
        if not sio.connected:  # Check connection status
            sio.connect(SOCKET_URL)  # Gunakan SOCKET_URL yang diimpor dari config_socket
            app_logger.info("Connected to Socket.IO server.")
        else:
            app_logger.info("Already connected to Socket.IO server.")
    except Exception as e:
        app_logger.error(f"Socket.IO connection failed: {e}")

if __name__ == "__main__":
    try:
        connect_socket()
        app.run(host="0.0.0.0", port=8100)  # Menjalankan Flask di port 5000
    except Exception as e:
        app_logger.error(f"Unexpected error: {e}")

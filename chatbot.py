import asyncio
import socketio
import paramiko
import smtplib

from datetime import datetime
from panoramisk import Manager
from asterisk.ami import AMIClient, SimpleAction
from collections import defaultdict
from models import RanablastCampaign, CustomerCall, RanablastContact, User, TaskTele, RoleUser, StatusCall, Role, StatusApplication
from config import Session
from loggers import bot_logger as logger
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from config_socket import sio
from panoramisk.message import Message

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import joinedload

ASTERISK_HOST = "172.16.203.199"
ASTERISK_PORT = 5038
ASTERISK_USERNAME = "ranatelapi"
ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"
ASTERISK_FOLDER = ""

# ASTERISK_HOST = "srv469501.hstgr.cloud"
# ASTERISK_PORT = 5038
# ASTERISK_USERNAME = "ranatelapi"
# ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"

# Fungsi untuk memulai kampanye autodialer
def start_bot_campaign(campaign_id):
    session = Session()
    try:
        asyncio.run(manage_bot(campaign_id=campaign_id))
    except SQLAlchemyError as e:
        logger.error(f"Database error in start_bot_campaign {campaign_id}: {e}")
    finally:
        session.close()
# Fungsi untuk menyelesaikan kampanye
def complete_bot_campaign(campaign_id):
    session = Session()
    try:
        campaign = session.query(RanablastCampaign).get(campaign_id)
        if campaign:
            campaign.status = "Completed"
            session.commit()
            logger.info(f"Kampanye {campaign_id} telah selesai.")
    except Exception as e:
        logger.info(f"Error in complete_bot_campaign {campaign_id}: {e}")
    finally:
        session.close()

def normalize_phone_number(phone_number):
    """
    Memodifikasi nomor telepon dengan aturan:
    - Jika nomor diawali dengan '30', hapus '30'.
    - Jika nomor diawali dengan '0', hapus '0'.
    """
    if phone_number.startswith("10"):
        return phone_number[2:]  # Hapus '30'
    elif phone_number.startswith("20"):
        return phone_number[2:]  # Hapus '0'
    elif phone_number.startswith("30"):
        return phone_number[2:]  # Hapus '0'
    elif phone_number.startswith("0"):
        return phone_number[1:]  # Hapus '0'
    return phone_number  # Tidak ada perubahan

def normalize_number(phone_number):
    """
    Fungsi untuk menormalisasi nomor telepon.
    Menghapus awalan 0 atau 62, hanya menyimpan nomor dengan awalan 8.
    """
    if phone_number.startswith('0'):
        phone_number = phone_number[1:]
    elif phone_number.startswith('62'):
        phone_number = phone_number[2:]
    
    # Hanya nomor dengan awalan 8 yang dianggap valid
    if not phone_number.startswith('8'):
        return None
    return phone_number

def is_connected(manager):
    try:
        response = manager.ping()  # Cek metode yang memastikan koneksi aktif
        return response is not None
    except Exception:
        return False

async def dial_number(manager, phone_number, campaign_id, provider, no_provider):
    try:
        full_number = f"{no_provider}{phone_number}"

        # Define the action to originate the call
        action = {
            "Action": "Originate",
            "Channel": f"PJSIP/{full_number}@{provider}",
            "Context": "wit-ai",
            "Exten": "s",
            "Priority": 1,
            "Async": "True",
            "CallerId": full_number,
        }

        # Send the action and await the response
        responses = await manager.send_action(action)
        logger.info(f"Responses: {responses}")

        # Check if responses is iterable (list/tuple)
        if not responses or not isinstance(responses, (list, tuple)):
            logger.info(f"Unexpected response format for {phone_number}: {responses}")
            return None
        
        # Process each response
        for response in responses:
            # Check if the response is of type 'Message'
            if isinstance(response, Message):
                action_id = response.get('ActionID')
                event = response.get('Event')
                response_status = response.get('Response')
                uniqueid = response.get('Uniqueid')
                logger.info(f"Received response: Event={event}, Status={response_status}, UniqueID={uniqueid}")

                # Process 'OriginateResponse' events with 'Success' status
                if event == 'OriginateResponse' and response_status == 'Success':
                    return uniqueid
            # If the response is a dictionary, process it
            elif isinstance(response, dict):
                event = response.get('Event')
                response_status = response.get('Response')
                if event == 'OriginateResponse' and response_status == 'Success':
                    return response.get('Uniqueid')
            else:
                logger.info(f"Unexpected response type for {phone_number}: {type(response)}")
    except Exception as e:
        logger.error(f"Error in dial_number {phone_number}: {e}")
    return None

def copy_audio_from_asterisk(remote_host, remote_path, local_path, username, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(remote_host, username=username, password=password)
    
    sftp = ssh.open_sftp()
    sftp.get(remote_path, local_path)
    sftp.close()
    ssh.close()

copy_audio_from_asterisk(ASTERISK_HOST, "/var/spool/asterisk/recordings/percakapan.wav", "/local/audio.wav", ASTERISK_USERNAME, ASTERISK_PASSWORD)

async def manage_bot(campaign_id, max_concurrent_calls=15):
    """
    Fungsi utama untuk mengelola autodialer dan menangani event Asterisk.
    """
    session = Session()

    campaign = session.query(RanablastCampaign).filter(RanablastCampaign.id==campaign_id).first()
    if not campaign or campaign.status != "Active":
        logger.info(f"Campaign {campaign_id} is not active or does not exist.")
        return

    manager = Manager(
        host=ASTERISK_HOST,
        port=ASTERISK_PORT,
        username=ASTERISK_USERNAME,
        secret=ASTERISK_PASSWORD,
    )

    logger.info("Connecting to Asterisk...")

    if not is_connected(manager):  # Cek apakah belum terhubung
        await manager.connect()
        logger.info("Successfully connected to Asterisk.")
    else:
        logger.info("Already connected to Asterisk.")

    call_status = {}

        # Speech-to-Text (STT)
    def transcribe_audio(file_path):
        recognizer = sr.Recognizer()
        with sr.AudioFile(file_path) as source:
            audio = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio, language="id-ID")
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            return "Error processing audio"

    # Natural Language Processing (NLP)
    def analyze_text(text):
        doc = nlp(text)
        if "harga" in text or "biaya" in text:
            return "Produk kami tersedia mulai dari Rp500.000. Apakah Anda tertarik?"
        elif "tidak tertarik" in text or "tidak perlu" in text:
            return "Baik, terima kasih atas waktunya."
        else:
            return "Bisa Anda jelaskan lebih lanjut?"

    # Text-to-Speech (TTS)
    def generate_speech(response_text):
        tts = gTTS(text=response_text, lang="id")
        file_path = "/var/lib/asterisk/sounds/response.mp3"
        tts.save(file_path)
        return file_path


    # Handler for when a key is pressed (DTMF tones)
    async def handle_dtmf(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"DTMF event: {event}")

    async def handle_varset(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"VarSet event: {event}")

    async def handle_hangup(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"Hangup event: {event}")

    async def handle_cdr(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"CDR event: {event}")

    async def handle_originate_response(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"CDR event: {event}")

    manager.register_event('DTMFBegin', handle_dtmf)
    manager.register_event('VarSet', handle_varset)
    manager.register_event('Hangup', handle_hangup)
    manager.register_event('Cdr', handle_cdr)
    manager.register_event('NewConnectedLine', handle_originate_response)

    try:
        contacts = session.query(RanablastContact).filter(RanablastContact.campaign_id==campaign_id, RanablastContact.contact_status=="Active").all()
        if not contacts:
            logger.info("No contacts to process in campaign.")
            return

        if all(contact.contact_status == "Completed" for contact in contacts):
            for contact in contacts:
                contact.contact_status = "Active"
            session.commit()

        contacts = [normalize_number(contact.CustomerCall6.hp) for contact in contacts if contact.CustomerCall6.status == "pending" or contact.CustomerCall6.status == "completed"]

        if not contacts:
            logger.info("No remaining contacts to call. Ending campaign.")
            return

        semaphore = asyncio.Semaphore(max_concurrent_calls)
    
        tasks = []

        async def process_call(number):
            async with semaphore:  # Batasi jumlah tugas yang berjalan bersamaan
                try:
                    result = await dial_number(manager, number, campaign_id, campaign.provider, campaign.no_provider)
                    if result is None:
                        logger.info(f"Calling {number} failed without Uniqueid.")
                    else:
                        logger.info(f"Called {number} done with Uniqueid: {result}")
                except Exception as e:
                    logger.error(f"Error while processing {number}: {e}")
                finally:
                    # Delay setelah setiap panggilan (jika diperlukan)
                    await asyncio.sleep(5)

        # Buat dan jalankan tugas-tugas secara paralel
        tasks = [asyncio.create_task(process_call(number)) for number in contacts]

        for task in tasks:
            # Hitung jumlah tugas yang masih berjalan
            running_tasks = len([t for t in tasks if not t.done()])
            logger.info(f'{running_tasks}/{max_concurrent_calls} calls in progress for campaign {campaign_id}.')
            await task
    except Exception as e:
        logger.error(f"Error managing autodialer for campaign {campaign_id}: {e}")
    finally:
        await asyncio.sleep(20)
        manager.close()
        logger.info("Manager connection closed.")

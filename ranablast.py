import asyncio
import socketio
from datetime import datetime
from panoramisk import Manager
from asterisk.ami import AMIClient, SimpleAction
from collections import defaultdict
from models import RanablastCampaign, CustomerCall, RanablastContact, User, TaskTele, RoleUser, StatusCall, Role, StatusApplication
from config import Session
from loggers import ranablast_logger as logger
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from config_socket import sio
from panoramisk.message import Message

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import joinedload

ASTERISK_HOST = "172.16.203.199"
ASTERISK_PORT = 5038
ASTERISK_USERNAME = "ranatelapi"
ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"

# ASTERISK_HOST = "srv469501.hstgr.cloud"
# ASTERISK_PORT = 5038
# ASTERISK_USERNAME = "ranatelapi"
# ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"

# Fungsi untuk memulai kampanye autodialer
def start_ranablast_campaign(campaign_id):
    session = Session()
    try:
        asyncio.run(manage_ranablast(campaign_id=campaign_id))
    except SQLAlchemyError as e:
        logger.error(f"Database error in start_ranablast_campaign {campaign_id}: {e}")
    finally:
        session.close()
# Fungsi untuk menyelesaikan kampanye
def complete_ranablast_campaign(campaign_id):
    session = Session()
    try:
        campaign = session.query(RanablastCampaign).get(campaign_id)
        if campaign:
            campaign.status = "Completed"
            session.commit()
            logger.info(f"Kampanye {campaign_id} telah selesai.")
    except Exception as e:
        logger.info(f"Error in complete_ranablast_campaign {campaign_id}: {e}")
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
            "Context": "ranablast",
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


async def manage_ranablast(campaign_id, max_concurrent_calls=15):
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

    # Handler for when a key is pressed (DTMF tones)
    async def handle_dtmf(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"DTMF event: {event}")
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')
                dtmf_digit = event.get('Digit')  # Get the digit pressed

                if not phone_number or not unique_id or not dtmf_digit:
                    campaign_logger.warning("DTMF event missing required fields")
                    return

                contact = (
                    session.query(RanablastContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(RanablastContact.campaign_id == campaign_id)
                    .first()
                )

                # Log the DTMF digit
                logger.info(f"DTMF digit {dtmf_digit} received from {phone_number} (Uniqueid: {unique_id})")

                # Perform action based on the DTMF digit pressed (e.g., option to transfer call)
                if dtmf_digit == '1':
                    logger.info(f"User pressed '1' for option 1.")
                    contact.contact_status = "Completed"
                    contact.call_result = "ANSWERED"

                    await send_message(campaign.name, contact.CustomerCall6.name, phone_number)

                    response_data = {
                        "nama": contact.CustomerCall6.name,
                        "result": contact.call_result,
                        "phone": phone_number,
                        "duration": contact.duration,
                        "campaign_id": campaign_id
                    }

                    # Ambil user aktif (status_active = 1)
                    active_users = (
                        session.query(User)
                        .join(RoleUser, RoleUser.model_id == User.id)  # Explicit join condition for RoleUser
                        .join(Role, Role.id == RoleUser.role_id)     # Explicit join condition for Role
                        .filter(Role.name.in_(['Superadmin', 'Developer']))  # Filter berdasarkan Role
                        .all()
                    )

                    if active_users:  # Jika ada pengguna aktif
                        for active_user in active_users:
                            user_id = active_user.id
                            sio.emit('result_data_ranablast', {'data': response_data, "user_id" : str(user_id)})
                            logger.info(f"Data sent to active user with ID {user_id}")
                    else:  # Jika tidak ada pengguna aktif
                        logger.info("No active user found. Data not sent.")
                    # Do something, e.g., transfer call or play a message
                elif dtmf_digit == '2':
                    logger.info(f"User pressed '2' for option 2.")
                    print("DAyumm")
                    await send_message(campaign.name, contact.CustomerCall6.name, phone_number)
                    # Do something else, e.g., play another message
                else:
                    logger.info(f"Unknown DTMF digit {dtmf_digit} pressed.")
            except Exception as e:
                logger.error(f"Error in handle_dtmf: {e}")
    async def handle_varset(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            logger.info(f"VarSet event: {event}")
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')
                variable_name = event.get('Variable')
                variable_value = event.get('Value')

                contact = (
                    session.query(RanablastContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(RanablastContact.campaign_id == campaign_id)
                    .first()
                )

                if variable_name == "UCAPAN" or variable_name == "RECOGNIZED_TEXT":
                    positive_responses = ["mau", "iya", "yes", "tentu", "minat", "iyo", "berminat", "boleh", "baik"]
                    if variable_value.lower() in positive_responses:
                        contact.contact_status = "Completed"
                        contact.call_result = "ANSWERED"
                        await send_mail_manager(contact.CustomerCall6.name, campaign.name)

                        response_data = {
                            "nama": contact.CustomerCall6.name,
                            "result": contact.call_result,
                            "phone": phone_number,
                            "duration": contact.duration,
                            "campaign_id": campaign_id
                        }

                        # Ambil user aktif (status_active = 1)
                        active_users = (
                            session.query(User)
                            .join(RoleUser, RoleUser.model_id == User.id)  # Explicit join condition for RoleUser
                            .join(Role, Role.id == RoleUser.role_id)     # Explicit join condition for Role
                            .filter(Role.name.in_(['Superadmin', 'Developer']))  # Filter berdasarkan Role
                            .all()
                        )

                        if active_users:  # Jika ada pengguna aktif
                            for active_user in active_users:
                                user_id = active_user.id
                                sio.emit('result_data_ranablast', {'data': response_data, "user_id" : str(user_id)})
                                logger.info(f"Data sent to active user with ID {user_id}")
                        else:  # Jika tidak ada pengguna aktif
                            logger.info("No active user found. Data not sent.")
            except Exception as e:
                logger.error(f"Error in handle_varset: {e}")
    async def handle_hangup(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')
                
                if not phone_number or not unique_id:
                    campaign_logger.warning("Hangup event missing required fields")
                    return

                contact = (
                    session.query(RanablastContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(RanablastContact.campaign_id == campaign_id)
                    .first()
                )

                if contact:
                    if contact.call_result not in ["ANSWERED", "VOICE MAIL"]:
                        call_status[unique_id] = 'Completed'
                        logger.info(f"Hangup Received for {event['Channel']} with Uniqueid {unique_id}: {event}")
                        contact.call_result = "NOT ANSWERED"
                        contact.contact_status = "Completed"
                        contact.duration = 0
                        
                        session.commit()

                        response_data = {
                            "nama": contact.CustomerCall6.name,
                            "status": contact.contact_status,
                            "result": contact.call_result,
                            "phone": phone_number,
                            "campaign_id": campaign_id
                        }

                        active_users = (
                            session.query(User)
                            .join(RoleUser, RoleUser.model_id == User.id)  # Explicit join condition for RoleUser
                            .join(Role, Role.id == RoleUser.role_id)     # Explicit join condition for Role
                            .filter(Role.name.in_(['Superadmin', 'Developer']))  # Filter berdasarkan Role
                            .all()
                        )

                        if active_users:  # Jika ada pengguna aktif
                            for active_user in active_users:
                                user_id = active_user.id
                                sio.emit('result_data_ranablast', {'data': response_data, "user_id" : str(user_id)})
                                logger.info(f"Data sent to active user with ID {user_id}")
                        else:  # Jika tidak ada pengguna aktif
                            logger.info("No active user found. Data not sent.")
                    else:
                        if call_status[unique_id] != 'Completed':
                            call_status[unique_id] = 'Completed'
                            contact.contact_status = "Completed"
            except SQLAlchemyError as e:
                logger.error(f"Database error in handle_hangup: {e}")
                session.rollback()
            except Exception as e:
                logger.error(f"Error in handle_hangup: {e}")
                session.rollback()
    async def handle_cdr(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            try:
                phone_number = normalize_phone_number(event.get('Source'))
                unique_id = event.get('Uniqueid')
                logger.info(phone_number)

                if not phone_number or not unique_id:
                    campaign_logger.warning("CDR event missing required fields")
                    return

                contact = (
                    session.query(RanablastContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(RanablastContact.campaign_id == campaign_id)
                    .first()
                )

                if contact:
                    logger.info(f"Cdr Received for {event['Channel']} with Uniqueid {unique_id}: {event}")
                    # Update duration only if it is currently 0
                    if contact.duration == 0:
                        contact.duration = event.get("Duration")
                    contact.contact_status = "Completed"
                    contact.call_result = "VOICE MAIL" if event.get('Destination') == 'machine' else event.get('Disposition')

                    session.commit()

                    response_data = {
                        "nama": contact.CustomerCall6.name,
                        "status": contact.contact_status,
                        "result": contact.call_result,
                        "phone": phone_number,
                        "duration": contact.duration,
                        "campaign_id": campaign_id
                    }

                    active_users = (
                        session.query(User)
                        .join(RoleUser, RoleUser.model_id == User.id)  # Explicit join condition for RoleUser
                        .join(Role, Role.id == RoleUser.role_id)     # Explicit join condition for Role
                        .filter(Role.name.in_(['Superadmin', 'Developer']))  # Filter berdasarkan Role
                        .all()
                    )

                    if active_users:  # Jika ada pengguna aktif
                        for active_user in active_users:
                            user_id = active_user.id
                            sio.emit('result_data_ranablast', {'data': response_data, "user_id" : str(user_id)})

                            logger.info(f"Data sent to active user with ID {user_id}")
                    else:  # Jika tidak ada pengguna aktif
                        logger.info("No active user found. Data not sent.")
            except SQLAlchemyError as e:
                logger.error(f"Database error in handle_cdr: {e}")
                session.rollback()
            except Exception as e:
                logger.error(f"Error in handle_cdr: {e}")
                session.rollback()
    async def handle_originate_response(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')

                if not phone_number:
                    campaign_logger.warning("OriginateResponse missing CallerIDNum")
                    return
                
                unique_id = event.get('Uniqueid')
                contact = (
                    session.query(RanablastContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(RanablastContact.campaign_id == campaign_id)
                    .first()
                )

                if contact and contact.contact_status not in ["Contacted", "Completed"]:
                    call_status[unique_id] = 'Initiated'
                    contact.contact_status = "Contacted"
                    contact.number_of_attempts += 1
                    contact.last_contacted = datetime.now()
                    session.commit()

                    response_data = {
                        "nama": contact.CustomerCall6.name,
                        "status": contact.contact_status,
                        "phone": phone_number,
                        "lastcall": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                        "campaign_id": campaign_id
                    }

                    # Ambil user aktif (status_active = 1)
                    active_users = (
                        session.query(User)
                        .join(RoleUser, RoleUser.model_id == User.id)  # Explicit join condition for RoleUser
                        .join(Role, Role.id == RoleUser.role_id)     # Explicit join condition for Role
                        .filter(Role.name.in_(['Superadmin', 'Developer']))  # Filter berdasarkan Role
                        .all()
                    )

                    if active_users:  # Jika ada pengguna aktif
                        for active_user in active_users:
                            user_id = active_user.id
                            sio.emit('result_data_ranablast', {'data': response_data, "user_id" : str(user_id)})
                            logger.info(f"Data sent to active user with ID {user_id}")
                    else:  # Jika tidak ada pengguna aktif
                        logger.info("No active user found. Data not sent.")
            except SQLAlchemyError as e:
                logger.error(f"Database error in handle_originate_response: {e}")
                session.rollback()
            except Exception as e:
                logger.error(f"Error in handle_originate_response: {e}")
                session.rollback()
    async def handle_channel_talking_start(manager,event):
        logger.info(f"ChannelTalkingStart Received for {event['Channel']} : {event}")
    async def handle_channel_talking_stop(manager,event):
        logger.info(f"ChannelTalkingStop Received for {event['Channel']} : {event}")
    async def handle_new_exten(manager,event):
        logger.info(f"GotoIf Received for {event['Channel']} : {event}")
        print(f"GotoIf Received for {event['Channel']} : {event}")
    async def handle_new_speech(manager,event):
        logger.info(f"SpeechRecognition Received for {event['Channel']} : {event}")
        print(f"SpeechRecognition Received for {event['Channel']} : {event}")

    manager.register_event('DTMFBegin', handle_dtmf)
    manager.register_event('VarSet', handle_varset)
    manager.register_event('Hangup', handle_hangup)
    manager.register_event('Cdr', handle_cdr)
    manager.register_event('NewConnectedLine', handle_originate_response)
    manager.register_event('ChannelTalkingStart', handle_channel_talking_start)
    manager.register_event('ChannelTalkingStop', handle_channel_talking_stop)
    manager.register_event('Newexten', handle_new_exten)
    manager.register_event('SpeechRecognition', handle_new_speech)

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



async def send_mail_manager(campaign_name, customer_name, phone_number):
    try:
        # Configurasi SMTP
        smtp_host = "ramusen.com"
        smtp_port = 465
        smtp_user = "noreply@ramusen.com"
        smtp_pass = "@noreply.12345"

        # Konfigurasi email
        mail_from = f"Pemberitahuan Kampanye <{smtp_user}>"
        mail_to = "giramnk@gmail.com"
        subject = f"Pemberitahuan Minat Kampanye {campaign_name}"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd;">
            <h2 style="color: #2c3e50;">Peringatan Minat Kampanye - Ranablast</h2>
            <p>Kepada Manajer Kampanye,</p>
            <p>Ada kontak yang menunjukkan minat pada kampanye Anda.</p>
            <div style="background-color: #f0f0f0; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
                <h4>Rincian Kontak:</h4>
                <p><strong>Nama:</strong> {customer_name}</p>
                <p><strong>Telepon:</strong> <a href="tel:{phone_number}">{phone_number}</a></p>
            </div>
            <p>Silakan hubungi mereka secepatnya.</p>
            <p>Salam,</p>
            <p><em>Sistem Kampanye Ranablast</em></p>
            <div style="margin-top: 20px; text-align: center;">
                <img src="https://ramusen.com/assets/img/logo.png?ver.2" alt="Logo Ranablast" style="width: 100px;" />
                <p style="color: #7f8c8d;">Ranablast - Menyambungkan Anda dengan Pelanggan</p>
            </div>
        </div>
        """

        # Kirim email
        msg = MIMEMultipart()
        msg["From"] = mail_from
        msg["To"] = mail_to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))

          # Kirim email menggunakan SMTP
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        server.login(smtp_user, smtp_pass)
        server.sendmail(mail_from, mail_to, msg.as_string())
        server.quit()
        
    except Exception as e:
        logger.error(f"Kesalahan saat mengirim email notifikasi: {e}")


async def send_message(campaign_name, customer_name, phone_number):
    url = "http://172.16.203.23:3000/send-message"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer $2b$10$PERWTF47Lict.8rJSOhbT.M4UJPjE.f5epdPH8AKxdsEknMXl2g2m"
    }
    
    message = f"""
    *Peringatan Minat Kampanye - {campaign_name}*

    Kepada Manajer Kampanye,

    Ada kontak yang menunjukkan minat pada kampanye Anda.

    📌 *Rincian Kontak:*
    - *Nama:* {customer_name}
    - *Telepon:* {phone_number}

    Silakan hubungi mereka secepatnya.

    Salam,
    _📝 Sistem Kampanye Ranablast_

    🌐 Ranablast - Menyambungkan Anda dengan Pelanggan
    """

    payload = {"number": "6281293062114", "message": message}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                data = await response.json()
                print(data.get("message", "Pesan terkirim."))
    except Exception as error:
        print("Error mengirim pesan:", error)

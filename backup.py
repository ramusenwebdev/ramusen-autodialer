import asyncio
import socketio
from datetime import datetime
from panoramisk import Manager
from asterisk.ami import AMIClient, SimpleAction
from collections import defaultdict
from models import AutoDialerCampaign, CustomerCall, AutoDialerProvider, AutoDialerContact, User, TaskTele
from config import Session
from loggers import autodialer_logger as logger
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from config_socket import sio

ASTERISK_HOST_TESTING = "172.16.203.199"
ASTERISK_PORT_TESTING = 5038
ASTERISK_USERNAME_TESTING = "ranatelapi"
ASTERISK_PASSWORD_TESTING = "343aa1aefe4908885015295abd578b91"

ASTERISK_HOST = "srv469501.hstgr.cloud"
ASTERISK_PORT = 5038
ASTERISK_USERNAME = "ranatelapi"
ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"
RECORDINGS_FOLDER = "/var/spool/asterisk/monitor/"

# SOCKET_URL = 'wss://www.ramusen.io/socket.io/'
# SOCKET_URL = 'wss://www.ramusen.io/socket.io/'


# sio = socketio.Client()

# Fungsi untuk memulai kampanye autodialer
def start_autodialer_campaign(campaign_id):
    session = Session()
    try:
        provider = session.query(AutoDialerProvider).filter(
            AutoDialerProvider.campaign_id == campaign_id
        ).first()

        if provider:
            logger.info(f"Starting campaign {campaign_id} with provider {provider.provider}.")
            asyncio.run(manage_autodialer(campaign_id=campaign_id, provider=provider.provider, no_provider=provider.no_provider, channel_group=provider.acd_group))
        else:
            logger.info(f"Campaign {campaign_id} has no active provider.")
    except SQLAlchemyError as e:
        logger.error(f"Database error in start_autodialer_campaign {campaign_id}: {e}")
    finally:
        session.close()
# Fungsi untuk menyelesaikan kampanye
def complete_campaign(campaign_id):
    session = Session()
    try:
        campaign = session.query(AutoDialerCampaign).get(campaign_id)
        if campaign:
            campaign.status = "Selesai"
            session.commit()
            logger.info(f"Kampanye {campaign_id} telah selesai.")
    except Exception as e:
        logger.info(f"Error in complete_campaign {campaign_id}: {e}")
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

async def dial_number(manager, phone_number, campaign_id, type_channel, no_provider, channel_group):
    full_number = f"{no_provider}{phone_number}"
    acd_group = "autodialer2" if type_channel == "Kreasi021" else "autodialer"
        
    action = {
        "Action": "Originate",
        "Channel": f"PJSIP/{full_number}@{type_channel}",
        "Context": acd_group,
        "Exten": "s",
        "Priority": 1,
        "Async": "True",
        "CallerId": full_number,
    }

    try:
        responses = await manager.send_action(action)

        if not responses:
            return None

        for response in responses:
            if (
                response.get('Event') == 'OriginateResponse' and 
                response.get('Response') == 'Success'
            ):
                unique_id = response.get('Uniqueid')
                return unique_id

        return None
    except Exception as e:
        logger.info(f"Error in dial_number {phone_number}: {e}")
        return None

async def manage_autodialer(campaign_id, provider, no_provider, channel_group, max_concurrent_calls=15):
    """
    Fungsi utama untuk mengelola autodialer dan menangani event Asterisk.
    """
    session = Session()

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

    # Before connecting, check if already connected to the Socket.IO server
    # if not sio.connected:  # Check connection status
    #     sio.connect(SOCKET_URL)
    #     logger.info("Connected to Socket.IO server.")
    # else:
    #     logger.info("Already connected to Socket.IO server.")
    
    call_status = {}

    async def handle_originate_response(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{provider}'):
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')

                if not phone_number:
                    campaign_logger.warning("OriginateResponse missing CallerIDNum")
                    return
                
                unique_id = event.get('Uniqueid')
                contact = (
                    session.query(AutoDialerContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(AutoDialerContact.campaign_id == campaign_id)
                    .first()
                )

                if contact and contact.contact_status not in ["Contacted", "Completed"]:
                    call_status[unique_id] = 'Initiated'
                    contact.contact_status = "Contacted"
                    contact.number_of_attempts += 1
                    contact.last_contacted = datetime.now()
                    session.commit()

                    response_data = {
                        "nama": contact.CustomerCall5.name,
                        "status": contact.contact_status,
                        "phone": phone_number,
                        "lastcall": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                        "campaign_id": campaign_id
                    }

                    # Ambil user aktif (status_active = 1)
                    active_users = session.query(User).filter(User.level == "Superuser", User.status_active == 1).all()

                    if active_users:  # Jika ada pengguna aktif
                        for active_user in active_users:
                            user_id = active_user.id
                            sio.emit('result_data_auto', {'data': response_data, "user_id" : str(user_id)})
                            logger.info(f"Data sent to active user with ID {user_id}")
                    else:  # Jika tidak ada pengguna aktif
                        logger.info("No active user found. Data not sent.")
            except SQLAlchemyError as e:
                logger.error(f"Database error in handle_originate_response: {e}")
                session.rollback()
            except Exception as e:
                logger.error(f"Error in handle_originate_response: {e}")
                session.rollback()

    async def handle_hangup(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{provider}'):
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')
                
                if not phone_number or not unique_id:
                    campaign_logger.warning("Hangup event missing required fields")
                    return

                contact = (
                    session.query(AutoDialerContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(AutoDialerContact.campaign_id == campaign_id)
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
                            "status": contact.contact_status,
                            "result": contact.call_result,
                            "phone": phone_number,
                            "campaign_id": campaign_id
                        }

                        active_users = session.query(User).filter(User.level == "Superuser", User.status_active == 1).all()

                        if active_users:  # Jika ada pengguna aktif
                            for active_user in active_users:
                                user_id = active_user.id
                                sio.emit('result_data_auto', {'data': response_data, "user_id" : str(user_id)})
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
        if event.get('Channel', '').startswith(f'PJSIP/{provider}'):
            try:
                
                phone_number = normalize_phone_number(event.get('Source'))
                unique_id = event.get('Uniqueid')
                logger.info(phone_number)

                if not phone_number or not unique_id:
                    campaign_logger.warning("CDR event missing required fields")
                    return

                contact = (
                    session.query(AutoDialerContact)
                    .join(CustomerCall)
                    .filter(or_(CustomerCall.hp.like(f'%{phone_number}'),
                                CustomerCall.hp.like(f'%0{phone_number}'),
                                CustomerCall.hp.like(f'%62{phone_number}')))
                    .filter(AutoDialerContact.campaign_id == campaign_id)
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
                        "status": contact.contact_status,
                        "result": contact.call_result,
                        "phone": phone_number,
                        "duration": contact.duration,
                        "campaign_id": campaign_id
                    }

                    active_users = session.query(User).filter(User.level == "Superuser", User.status_active == 1).all()

                    if active_users:  # Jika ada pengguna aktif
                        for active_user in active_users:
                            user_id = active_user.id
                            sio.emit('result_data_auto', {'data': response_data, "user_id" : str(user_id)})

                            logger.info(f"Data sent to active user with ID {user_id}")
                    else:  # Jika tidak ada pengguna aktif
                        logger.info("No active user found. Data not sent.")
            except SQLAlchemyError as e:
                logger.error(f"Database error in handle_cdr: {e}")
                session.rollback()
            except Exception as e:
                logger.error(f"Error in handle_cdr: {e}")
                session.rollback()

    async def handle_agent_connect(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{provider}'):
            try:
                agent_connect = event.get('ConnectedLineNum')
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                agent_connect = str(agent_connect)
                agent = session.query(User).filter(User.channel_account==agent_connect, User.status_active == 1).first()
                print(f"Agent Details: id={agent.id}, username={agent.username}, status_active={agent.status_active}")

                if agent:
                    logger.info(f"Agent Answer Received for {event['Channel']} : {event}")

                    customer = session.query(CustomerCall).filter(
                        or_(
                            CustomerCall.hp.like(f'%{phone_number}'),
                            CustomerCall.hp.like(f'%0{phone_number}'),
                            CustomerCall.hp.like(f'%62{phone_number}')
                        )
                    ).first()
                    if customer:
                        contact = session.query(AutoDialerContact).filter_by(
                            customer_call_id=customer.id,
                            campaign_id=campaign_id
                        ).first()

                        if contact:
                            contact.agent = agent.username  # Associate the agent
                        else:
                            logger.info(f"Contact not found for customer {customer.name} and campaign {campaign_id}")
                        
                        # Send customer data to the agent
                        data_customer = {
                            "name": customer.name,
                            "phone": customer.hp,
                            "company": customer.company_name,
                            "dob": customer.dob,
                        }

                        sio.emit("customer_data_auto", {"data": data_customer, "user_id": str(agent.id)})
                        # Create a new task for this interaction
                        new_task = TaskTele(
                            customer_call_id=customer.id,
                            user_id=agent.id,
                            submitted_dt=now,
                            status_call=7,  # Status "connected"
                            approved="Done",
                            loan=0,
                            lastupduser=agent.id,
                            lastupddttm=now,
                        )
                        session.add(new_task)
                        session.commit()

                        logger.info(f"TaskTele entry created for customer {customer.name} and agent {agent.username}")
                    else:
                        logger.info(f"Customer not found for phone number {phone_number}")
                else:
                    print(f"Agent {agent_connect} is not active or not found.")
                    logger.info(f"Agent {agent_connect} is not active or not found.")
            except SQLAlchemyError as e:
                logger.error(f"Database error in handle_agent_connect: {e}")
                session.rollback()
            except Exception as e:
                logger.error(f"Error in handle_agent_connect: {e}")
                session.rollback()

    async def handle_agent_completed(manager,event) :
        logger.info(f"Agent Completed Received for {event['Channel']} : {event}")

    manager.register_event('Hangup', handle_hangup)
    manager.register_event('NewConnectedLine', handle_originate_response)
    manager.register_event('Cdr', handle_cdr)
    manager.register_event('AgentConnect', handle_agent_connect)
    manager.register_event('AgentComplete', handle_agent_completed)

    try:
        campaign = session.query(AutoDialerCampaign).filter(AutoDialerCampaign.id==campaign_id).first()
        if not campaign or campaign.status != "Active":
            logger.info(f"Campaign {campaign_id} is not active or does not exist.")
            return

        contacts = session.query(AutoDialerContact).filter(AutoDialerContact.campaign_id==campaign_id, AutoDialerContact.contact_status=="Active").all()
        if not contacts:
            logger.info("No contacts to process in campaign.")
            return

        if all(contact.contact_status == "Completed" for contact in contacts):
            for contact in contacts:
                contact.contact_status = "Active"
            session.commit()

        contacts = [normalize_number(contact.CustomerCall5.hp) for contact in contacts if contact.contact_status == "Active" or contact.contact_status == "Contacted"]

        if not contacts:
            logger.info("No remaining contacts to call. Ending campaign.")
            return

        semaphore = asyncio.Semaphore(max_concurrent_calls)
    
        tasks = []

        async def process_call(number):
            async with semaphore:  # Batasi jumlah tugas yang berjalan bersamaan
                try:
                    result = await dial_number(manager, number, campaign_id, provider, no_provider, channel_group)
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
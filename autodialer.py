import asyncio
import socketio
from datetime import datetime
from panoramisk import Manager
from asterisk.ami import AMIClient, SimpleAction
from collections import defaultdict
from models import AutoDialerCampaign, CustomerCall, AutoDialerContact, AutoDialerContactFlag, User, TaskTele, RoleUser, StatusCall, Role, StatusApplication
from config import Session
from loggers import autodialer_logger as logger
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from config_socket import sio
from panoramisk.message import Message

# ASTERISK_HOST = "172.16.203.199"
# ASTERISK_PORT = 5038
# ASTERISK_USERNAME = "ranatelapi"
# ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"

ASTERISK_HOST = "srv469501.hstgr.cloud"
ASTERISK_PORT = 5038
ASTERISK_USERNAME = "ranatelapi"
ASTERISK_PASSWORD = "343aa1aefe4908885015295abd578b91"
RECORDINGS_FOLDER = "/var/spool/asterisk/monitor/"

# Fungsi untuk memulai kampanye autodialer
def start_autodialer_campaign(campaign_id):
    session = Session()
    try:
        asyncio.run(manage_autodialer(campaign_id=campaign_id))
    except SQLAlchemyError as e:
        logger.error(f"Database error in start_autodialer_campaign {campaign_id}: {e}")
    finally:
        session.close()
# Fungsi untuk menyelesaikan kampanye
def complete_autodialer_campaign(campaign_id):
    session = Session()
    try:
        campaign = session.query(AutoDialerCampaign).get(campaign_id)
        if campaign:
            campaign.status = "Completed"
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

async def dial_number(manager, phone_number, campaign_id, provider, no_provider, channel_group):
    try:
        full_number = f"{no_provider}{phone_number}"

        action = {
            "Action": "Originate",
            "Channel": f"PJSIP/{full_number}@{provider}",
            "Context": channel_group,
            "Exten": "s",
            "Priority": 1,
            "Async": "True",
            "CallerId": full_number,
        }

        responses = await manager.send_action(action)

        # Periksa apakah responses adalah iterable (list atau dictionary)
        if not responses or not isinstance(responses, (list, tuple)):
            logger.info(f"Unexpected response format for {phone_number}: {responses}")
            return None

        # Proses response jika tipe data sudah benar
        for response in responses:
            if isinstance(response, dict):  # Pastikan response adalah dictionary
                if response.get('Event') == 'OriginateResponse' and response.get('Response') == 'Success':
                    return response.get('Uniqueid')
            else:
                logger.info(f"Unexpected response type for {phone_number}: {type(response)}")
    except Exception as e:
        logger.info(f"Error in dial_number {phone_number}: {e}")
    return None

async def manage_autodialer(campaign_id, max_concurrent_calls=15):
    """
    Fungsi utama untuk mengelola autodialer dan menangani event Asterisk.
    """
    session = Session()

    campaign = session.query(AutoDialerCampaign).filter(AutoDialerCampaign.id==campaign_id).first()
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

    async def handle_originate_response(manager, event):
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            try:
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                unique_id = event.get('Uniqueid')
                now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

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

                    response_data = {
                        "nama": contact.CustomerCall5.name,
                        "status": contact.contact_status,
                        "phone": phone_number,
                        "lastcall": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                        "campaign_id": campaign_id
                    }

                    # Create a new task for this interaction
                    flag_contact = AutoDialerContactFlag(
                        campaign_id=campaign.id,
                        customer_id=contact.customer_id,
                        created_at=now,
                        updated_at=now,
                    )
                    
                    session.add(flag_contact)

                    session.commit()

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
                            sio.emit('result_data_autodialer', {'data': response_data, "user_id" : str(user_id)})
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
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
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
                            "nama": contact.CustomerCall5.name,
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
                                sio.emit('result_data_autodialer', {'data': response_data, "user_id" : str(user_id)})
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
                        "nama": contact.CustomerCall5.name,
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
                            sio.emit('result_data_autodialer', {'data': response_data, "user_id" : str(user_id)})

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
        if event.get('Channel', '').startswith(f'PJSIP/{campaign.provider}'):
            try:
                agent_connect = event.get('ConnectedLineNum')
                phone_number = normalize_phone_number(event.get('CallerIDNum'))
                now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

                agent_connect = str(agent_connect)
                agent = session.query(User).filter(User.channel_account==agent_connect).first()

                status_call = session.query(StatusCall).filter(StatusCall.name=="Follow Up").first()

                status_application = session.query(StatusApplication).filter(StatusApplication.name=="Approved").first()

                print(f"Agent Details: id={agent.id}, username={agent.username}")

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
                        customer.status = 'completed'
                        contact = session.query(AutoDialerContact).filter(
                            AutoDialerContact.customer_id == customer.id,
                            AutoDialerContact.campaign_id == campaign_id
                        ).first()

                        if contact:
                            contact.tele_id = agent.id  # Associate the agent
                            contact.call_result = "ANSWERED"
                            contact.contact_status = "Completed"
                        else:
                            logger.info(f"Contact not found for customer {customer.name} and campaign {campaign_id} with agent {agent.id}")
                        # Send customer data to the agent
                        data_customer = {
                            "name": customer.name,
                            "phone": customer.hp,
                            "company": customer.company_name,
                            "dob": customer.dob.strftime("%Y-%m-%d") if customer.dob else None,  # Konversi date ke string
                        }

                        sio.emit("customer_data_autodialer", {"data": data_customer, "user_id": str(agent.id)})
                        # Create a new task for this interaction
                        new_task = TaskTele(
                            user_id=agent.id,
                            customer_id=customer.id,
                            status_call_id=status_call.id,
                            status_application_id=3,
                            loan=0,
                            notes="",
                            batch_processed_at=now,
                            created_at=now,
                            updated_at=now,
                        )
                        
                        session.add(new_task)
                        session.commit()

                        response_data = {
                            "phone": phone_number,
                            "tele": agent.username,
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
                                sio.emit('result_data_autodialer', {'data': response_data, "user_id" : str(user_id)})
                                logger.info(f"Data sent to active user with ID {user_id}")
                        else:  # Jika tidak ada pengguna aktif
                            logger.info("No active user found. Data not sent.")
                            
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
        contacts = session.query(AutoDialerContact).filter(AutoDialerContact.campaign_id==campaign_id, AutoDialerContact.contact_status=="Active").all()
        if not contacts:
            logger.info("No contacts to process in campaign.")
            return

        if all(contact.contact_status == "Completed" for contact in contacts):
            for contact in contacts:
                contact.contact_status = "Active"
            session.commit()

        contacts = [normalize_number(contact.CustomerCall5.hp) for contact in contacts if contact.CustomerCall5.status == "pending" or contact.CustomerCall5.status == "completed"]

        if not contacts:
            logger.info("No remaining contacts to call. Ending campaign.")
            return

        semaphore = asyncio.Semaphore(max_concurrent_calls)
    
        tasks = []

        async def process_call(number):
            async with semaphore:  # Batasi jumlah tugas yang berjalan bersamaan
                try:
                    result = await dial_number(manager, number, campaign_id, campaign.provider, campaign.no_provider, campaign.channel_group)
                    if result is None:
                        logger.info(f"Calling {number} failed without Uniqueid.")
                    else:
                        logger.info(f"Called {number} done with Uniqueid: {result}")
                except Exception as e:
                    logger.error(f"Error while processing {number}: {e}")
                finally:
                    # Delay setelah setiap panggilan (jika diperlukan)
                    await asyncio.sleep(10)

        # Buat dan jalankan tugas-tugas secara paralel
        tasks = [asyncio.create_task(process_call(number)) for number in contacts]
        try:
            # Tunggu semua task selesai, tetapi bisa dihentikan jika kampanye berubah status
            while True:
                if not campaign or campaign.status != "Active":
                    logger.info(f"Campaign {campaign_id} is not active or does not exist. Cancelling tasks...")
                    
                    # Membatalkan semua task yang masih berjalan
                    for task in tasks:
                        task.cancel()
                    
                    # Tunggu semua task selesai setelah dibatalkan
                    await asyncio.gather(*tasks, return_exceptions=True)
                    return

                # Hitung jumlah task yang masih berjalan
                running_tasks = sum(1 for t in tasks if not t.done())
                logger.info(f'{running_tasks}/{max_concurrent_calls} calls in progress for campaign {campaign_id}.')
                # Tunggu sebentar sebelum memeriksa kembali status kampanye
                await asyncio.sleep(1)

            # Tunggu semua task selesai sebelum melanjutkan
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info(f"Campaign {campaign_id} tasks were cancelled.")

        # for task in tasks:
        #     # Hitung jumlah tugas yang masih berjalan
        #     running_tasks = len([t for t in tasks if not t.done()])
        #     logger.info(f'{running_tasks}/{max_concurrent_calls} calls in progress for campaign {campaign_id}.')
        #     await task
    except Exception as e:
        logger.error(f"Error managing autodialer for campaign {campaign_id}: {e}")
    finally:
        await asyncio.sleep(20)
        manager.close()
        logger.info("Manager connection closed.")
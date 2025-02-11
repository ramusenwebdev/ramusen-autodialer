import socketio
import time
import random
from datetime import datetime

# SOCKET_URL = 'wss://www.ramusen.io/socket.io/'
# SOCKET_URL = 'ws://localhost:5000/socket.io/'
SOCKET_URL = 'ws://localhost:5000/socket.io/'

count = 0
MAX_ITERATIONS = 2000  # Berhenti setelah 2000 pengiriman
BATCH_SIZE = 1  # Mengirimkan 15 data sekaligus dalam satu perulangan
CAMPAIGN_ID = 112  # Campaign ID yang sama untuk semua data

# Daftar status untuk diacak
STATUS_OPTIONS = ["Completed", "Active", "Contacted"]
RESULT_OPTIONS = ["ANSWERED", "VOICE MAIL", "NOT ANSWERED"]
# Inisialisasi koneksi Socket.IO
sio = socketio.Client()

# Callback untuk koneksi berhasil
@sio.event
def connect():
    global count
    print("Connected to Socket.IO server")

    while count < MAX_ITERATIONS:
        # Membuat 15 data secara sekaligus (batch)
        contacted_data = []
        phone_number = f"0812{random.randint(10000000, 99999999)}"
        user_no = count + 1
        for i in range(BATCH_SIZE):

            # Data dengan status "Contacted" dan result null
            response_data_contacted = {
                "nama": f"User {user_no}",
                "status": "Contacted",
                "phone": phone_number,
                "result": None,  # Result null untuk status "Contacted"
                "lastcall": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "campaign_id": CAMPAIGN_ID
            }
            
            contacted_data.append(response_data_contacted)
            count += 1  # Menambah counter untuk setiap data

        # Kirim batch data "Contacted" (15 data sekaligus)
        for data in contacted_data:
            sio.emit("result_data_auto", {"data": data, "user_id": 62})
            print(f"Contacted Data sent: {data}")

        # Tunggu 5 detik sebelum mengirim batch berikutnya
        time.sleep(5)  # Tunggu 5 detik antara pengiriman "Contacted" dan "Completed"

         # Membuat 15 data dengan status "Completed"
        completed_data = []
        for i in range(BATCH_SIZE):
            # Data dengan status "Completed" dan hasil tertentu
            response_data_completed = {
                "nama": f"User {user_no}",
                "status": "Completed",
                "phone": phone_number,
                "result": random.choice(RESULT_OPTIONS),  # Mengatur result untuk status "Completed"
                "lastcall": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "campaign_id": CAMPAIGN_ID
            }
            
            completed_data.append(response_data_completed)
            count += 1  # Menambah counter untuk setiap data

        # Kirim batch data "Completed" (15 data sekaligus)
        for data in completed_data:
            sio.emit("result_data_auto", {"data": data, "user_id": 62})
            print(f"Completed Data sent: {data}")

        # Tunggu jika perlu untuk beberapa detik sebelum memulai batch berikutnya
        time.sleep(5)  # Tunggu 5 detik antara batch pengiriman "Contacted" dan "Completed"

        # Cek jika sudah mencapai total iterasi yang diinginkan
        if count >= MAX_ITERATIONS * BATCH_SIZE * 2:  # Total data = 15 Contacted + 15 Completed per iterasi
            break

    print("Max iterations reached. Disconnecting...")
    sio.disconnect()

# Callback untuk koneksi terputus
@sio.event
def disconnect():
    print("Disconnected from Socket.IO server")

# Callback untuk menangani error
@sio.event
def connect_error(data):
    print(f"Connection failed: {data}")

# Callback untuk menangani konfirmasi pengiriman data
@sio.event
def customer_data_response(data):
    print(f"Response received: {data}")
    sio.disconnect()  # Disconnect setelah data berhasil dikirim

# Main function
def main():
    try:
        # Connect ke server
        sio.connect(SOCKET_URL)
        sio.wait()  # Tunggu event terjadi
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Disconnect dari server jika sudah selesai
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    main()

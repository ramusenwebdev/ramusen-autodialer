import requests
import json

def send_message(phone):
    if not phone:
        print("Harap isi nomor HP dan pesan.")
        return
    
    customer_name = "Gira"
    phone_number = "081293062114"
    url = "http://172.16.203.23:3000/send-message"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer $2b$10$PERWTF47Lict.8rJSOhbT.M4UJPjE.f5epdPH8AKxdsEknMXl2g2m"
    }
    message = f"""
        *Peringatan Minat Kampanye - Ranablast*

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

    payload = {"number": phone, "message": message}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        data = response.json()
        logger.info(data.get("message", "Pesan terkirim."))
    except Exception as error:
        logger.info("Error mengirim pesan:", error)

# Contoh pemanggilan fungsi
send_message("6281293955090")
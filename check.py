import os
from asterisk.ami import AMIClient, SimpleAction

# Konfigurasi AMI
#AMI_HOST = os.getenv('AMI_HOST', 'srv469501.hstgr.cloud')
#AMI_PORT = int(os.getenv('AMI_PORT', 5038))
#AMI_USER = os.getenv('AMI_USER', 'ranatelapi')
#AMI_PASSWORD = os.getenv('AMI_PASSWORD', '343aa1aefe4908885015295abd578b91')
AMI_HOST = 'srv469501.hstgr.cloud'
AMI_PORT = 5038
AMI_USER = 'ranatelapi'
AMI_PASSWORD = '343aa1aefe4908885015295abd578b91'

def check_active_calls():
    client = AMIClient(address=AMI_HOST, port=AMI_PORT)
    try:
        client.login(AMI_USER, AMI_PASSWORD)
        action = SimpleAction('Command', Command='core show channels')
        response = client.send_action(action)

        # Tunggu hingga FutureResponse terpecahkan
        resolved_response = response.get_response()

        # Ambil output dari response
        output = resolved_response.keys.get('Output', None)

        if output:
            output_lines = output.splitlines()
            active_calls_count = 0
            #active_channels = None
            filtered_lines = []
            
            for line in output_lines:
                if 'PJSIP/DALnet021' in line:
                # if 'PJSIP/Kreasi021' in line:
                    active_calls_count += 1
                
                # Mencari active channels
                if 'active channels' in line:
                    active_channels = line.split()[0]  # Ambil angka pertama
                
                if '' in line:
                    filtered_lines.append(line)

            # Tampilkan hasil
            print(f"")
            #print(f"Total Active Call(s) on DALnet : {active_calls_count}")
            print(f"Total Active Call(s) on Kreasi : {active_calls_count}")
            print(f"Detail Active Call(s) : ")
            #if active_channels is not None:
                #print(f"Active Channel(s): {active_channels}")
            #else:
                #print("Active Channels not found.")

            if filtered_lines:
                for line in filtered_lines:
                    print(line)
                    #print(f" - {(line.split()[0])[((line.split()[0]).find("PJSIP/") + len("PJSIP/")):(line.split()[0]).find("-")]} to {(line.split()[3])[((line.split()[3]).find("PJSIP/") + len("PJSIP/")):(line.split()[3]).find("@DAL")]} status {line.split()[2]}")
                print(f"")
            else:
                print("*** No active lines ***")
                print(f"")

        else:
            print("No output found in the response.")

    except Exception as e:
        print(f"Error during AMI action: {e}")
    finally:
        client.logoff()

if __name__ == "__main__":
    check_active_calls()
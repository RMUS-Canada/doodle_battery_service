import tkinter as tk
from tkinter import messagebox
import paramiko

# Function to create credentials file and run nmcli
def configure_radio():
    host = entry_host.get()
    ssh_username = entry_ssh_username.get()
    ssh_password = entry_ssh_password.get()

    radio_ip_address = entry_radio_ip.get()
    radio_rpc_username = entry_radio_username.get()
    radio_rpc_password = entry_radio_password.get()
    
    ip_address = entry_ip.get()

    if not all([host, ssh_username, ssh_password, radio_rpc_username, radio_rpc_password, radio_ip_address, ip_address]):
        messagebox.showerror("Error", "Please fill in all fields.")
        return

    credentials_content = f"{radio_ip_address}\n{radio_rpc_username}\n{radio_rpc_password}\n"
    credentials_path = "/persist/opt/doodle_rpc_credentials"
    nmcli_mod_cmd = f"nmcli con mod eth-robot +ipv4.addresses {ip_address}/16"
    nmcli_up_cmd = "nmcli con up eth-robot"

    try:
        # Connect via SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=ssh_username, password=ssh_password)

        # Write credentials to a temp file
        temp_path = f"/tmp/doodle_rpc_credentials"
        sftp = ssh.open_sftp()
        with sftp.file(temp_path, 'w') as f:
            f.write(credentials_content)
        sftp.close()

        # Move credentials file to /etc with sudo and set permissions
        move_cmd = f"sudo -S mv {temp_path} {credentials_path} && sudo -S chmod 600 {credentials_path}"
        stdin, stdout, stderr = ssh.exec_command(move_cmd, get_pty=True)
        stdin.write(f'{ssh_password}\n')
        stdin.flush()
        stdout.channel.recv_exit_status()
        move_err = stderr.read().decode()
        if move_err:
            raise Exception(f"Error moving credentials file: {move_err}")

        # Run nmcli mod command
        nmcli_mod_full = f"sudo -S {nmcli_mod_cmd}"
        stdin, stdout, stderr = ssh.exec_command(nmcli_mod_full, get_pty=True)
        stdin.write(f'{ssh_password}\n')
        stdin.flush()
        mod_out = stdout.read().decode()
        mod_err = stderr.read().decode()
        if mod_err:
            raise Exception(f"nmcli error: {mod_err}")

        # Run nmcli up command
        nmcli_up_full = f"sudo -S {nmcli_up_cmd}"
        stdin, stdout, stderr = ssh.exec_command(nmcli_up_full, get_pty=True)
        stdin.write(f'{ssh_password}\n')
        stdin.flush()
        up_out = stdout.read().decode()
        up_err = stderr.read().decode()
        if up_err:
            raise Exception(f"nmcli up error: {up_err}")

        ssh.close()
        messagebox.showinfo("Success", f"Configuration complete!\n\nMake sure to restart the doodle_battery_service extension from CORE I/O's webpage.")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def undo_configuration():
    confirm = messagebox.askyesno(
        "Confirm Undo",
        "Are you sure you want to undo the configuration?\nThis will remove the credentials and network address from the CORE I/O."
    )
    if not confirm:
        return
    host = entry_host.get()
    ssh_username = entry_ssh_username.get()
    ssh_password = entry_ssh_password.get()
    ip_address = entry_ip.get()
    credentials_path = "/persist/opt/doodle_rpc_credentials"
    nmcli_remove_cmd = f"nmcli con mod eth-robot -ipv4.addresses {ip_address}/16"
    nmcli_up_cmd = "nmcli con up eth-robot"

    if not all([host, ssh_username, ssh_password, ip_address]):
        messagebox.showerror("Error", "Please fill in all fields (except radio credentials) to undo configuration.")
        return

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=ssh_username, password=ssh_password)

        # Delete credentials file
        del_cmd = f"sudo -S rm -f {credentials_path}"
        stdin, stdout, stderr = ssh.exec_command(del_cmd, get_pty=True)
        stdin.write(f'{ssh_password}\n')
        stdin.flush()
        stdout.channel.recv_exit_status()
        del_err = stderr.read().decode()
        if del_err:
            raise Exception(f"Error deleting credentials file: {del_err}")

        # Remove IP address from eth-robot
        nmcli_remove_full = f"sudo -S {nmcli_remove_cmd}"
        stdin, stdout, stderr = ssh.exec_command(nmcli_remove_full, get_pty=True)
        stdin.write(f'{ssh_password}\n')
        stdin.flush()
        remove_out = stdout.read().decode()
        remove_err = stderr.read().decode()
        if remove_err:
            raise Exception(f"nmcli remove error: {remove_err}")
        
        # Run nmcli up command
        nmcli_up_full = f"sudo -S {nmcli_up_cmd}"
        stdin, stdout, stderr = ssh.exec_command(nmcli_up_full, get_pty=True)
        stdin.write(f'{ssh_password}\n')
        stdin.flush()
        up_out = stdout.read().decode()
        up_err = stderr.read().decode()
        if up_err:
            raise Exception(f"nmcli up error: {up_err}")

        ssh.close()
        messagebox.showinfo("Undo Success", f"Configuration undone!\n\nMake sure to restart the doodle_battery_service extension from CORE I/O's webpage.")
    except Exception as e:
        messagebox.showerror("Error", str(e))

# GUI setup
root = tk.Tk()
root.title("CORE I/O Doodle Config Tool")
root.geometry("400x400")
root.resizable(False, False)

# --- CORE I/O Connection Frame ---
frame_coreio = tk.LabelFrame(root, text="CORE I/O Connection", padx=10, pady=10)
frame_coreio.pack(fill='x', padx=10, pady=(10, 5))

label_host = tk.Label(frame_coreio, text="CORE I/O IP Address:", width=22, anchor='w')
label_host.grid(row=0, column=0, sticky='w')
entry_host = tk.Entry(frame_coreio, width=28)
entry_host.grid(row=0, column=1, pady=2)

label_ssh_username = tk.Label(frame_coreio, text="CORE I/O Username:", width=22, anchor='w')
label_ssh_username.grid(row=1, column=0, sticky='w')
entry_ssh_username = tk.Entry(frame_coreio, width=28)
entry_ssh_username.grid(row=1, column=1, pady=2)

label_ssh_password = tk.Label(frame_coreio, text="CORE I/O Password:", width=22, anchor='w')
label_ssh_password.grid(row=2, column=0, sticky='w')
entry_ssh_password = tk.Entry(frame_coreio, width=28, show='*')
entry_ssh_password.grid(row=2, column=1, pady=2)

# --- Doodle Radio Frame ---
frame_radio = tk.LabelFrame(root, text="Doodle Radio", padx=10, pady=10)
frame_radio.pack(fill='x', padx=10, pady=5)

label_radio_ip = tk.Label(frame_radio, text="Doodle Radio IP on Spot:", width=22, anchor='w')
label_radio_ip.grid(row=0, column=0, sticky='w')
entry_radio_ip = tk.Entry(frame_radio, width=28)
entry_radio_ip.grid(row=0, column=1, pady=2)

label_radio_username = tk.Label(frame_radio, text="Doodle RPC Username:", width=22, anchor='w')
label_radio_username.grid(row=1, column=0, sticky='w')
entry_radio_username = tk.Entry(frame_radio, width=28)
entry_radio_username.grid(row=1, column=1, pady=2)

label_radio_password = tk.Label(frame_radio, text="Doodle RPC Password:", width=22, anchor='w')
label_radio_password.grid(row=2, column=0, sticky='w')
entry_radio_password = tk.Entry(frame_radio, width=28, show='*')
entry_radio_password.grid(row=2, column=1, pady=2)

# --- Network Frame ---
frame_network = tk.LabelFrame(root, text="Network", padx=10, pady=10)
frame_network.pack(fill='x', padx=10, pady=5)

label_ip = tk.Label(frame_network, text="IP for CORE I/O (10.223.X.Y):", width=22, anchor='w')
label_ip.grid(row=0, column=0, sticky='w')
entry_ip = tk.Entry(frame_network, width=28)
entry_ip.grid(row=0, column=1, pady=2)

# --- Buttons Frame ---
frame_buttons = tk.Frame(root)
frame_buttons.pack(pady=15)

configure_btn = tk.Button(frame_buttons, text="Configure", command=configure_radio, bg='#4CAF50', fg='white', width=18, height=2)
configure_btn.pack(side='left', padx=10)

undo_btn = tk.Button(frame_buttons, text="Undo Configuration", command=undo_configuration, bg='#f44336', fg='white', width=18, height=2)
undo_btn.pack(side='left', padx=10)

root.mainloop() 
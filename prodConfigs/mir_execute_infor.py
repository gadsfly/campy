import subprocess
import csv

# Step 1: Ask user for information
user_info = {}
user_info['animalname'] = input("Enter animal: ")
user_info['email'] = input("Enter email: ")
# Add more fields as needed

# Step 2: Write to metadata file
with open('metadata.txt', 'w') as f:
    f.write(f"Name: {user_info['name']}\n")
    f.write(f"Email: {user_info['email']}\n")
    # Write other metadata fields as needed

# Step 3: Save to CSV file
with open('data.csv', 'w', newline='') as csvfile:
    fieldnames = ['Name', 'Email']  # Define your CSV headers
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    
    writer.writeheader()
    writer.writerow({'Name': user_info['name'], 'Email': user_info['email']})
    # Write additional rows if there are more fields

# Step 4: Activate Conda environment
activate_cmd = 'conda activate campy_fix'
subprocess.run(activate_cmd, shell=True)

# Step 5: Execute campy-acquire
config_path = 'C:\Users\as1296\campy-master\campy-master\prodConfigs\prod_recordcopy_campy_custom_config_flir6cam.yaml'  # Replace with your actual config path
acquire_cmd = f'campy-acquire {config_path}'
subprocess.run(acquire_cmd, shell=True)

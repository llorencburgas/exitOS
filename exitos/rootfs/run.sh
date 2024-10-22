#!/usr/bin/with-contenv bashio

echo "Creem la carpeta (/share/exitos/) si no existeix, aqui guardarem fitxers persistents."
mkdir -p /share/exitos/

# Declare variables
# declare Consumer_asset_IDs
# declare Generator_asset_IDs
# declare Energy_Source_asset_IDs
# declare Building_consumption_IDs
# declare Building_generation_IDs

# Define configuration file 
# config_file="/share/exitos/user_info.conf"
# if [ -f "$config_file" ]; then
   # echo "Llegint dades de configuració des de $config_file"

   #read values
   # Consumer_asset_IDs=$(awk -F "=" '/AssetID/ {print $2}' "$config_file" | tr -d ' ')
   # Generator_asset_IDs=$(awk -F "=" '/GeneratorID/ {print $2}' "$config_file" | tr -d ' ')
   # Energy_Source_asset_IDs=$(awk -F "=" '/SourceID/ {print $2}' "$config_file" | tr -d ' ')
   # Building_consumption_IDs=$(awk -F "=" '/BuildingConsumptionID/ {print $2}' "$config_file" | tr -d ' ')
   # Building_generation_IDs=$(awk -F "=" '/BuildingGenerationID/ {print $2}' "$config_file" | tr -d ' ')

   # echo "Dades carregades:"
   # echo "Asset ID: $Consumer_asset_IDs"
   # echo "Generator ID: $Generator_asset_IDs"
   # echo "Source ID: $Energy_Source_asset_IDs"
   # echo "Building Consumption ID: $Building_consumption_IDs"
   # echo "Building Generation ID: $Building_generation_IDs"

   # echo "Starting main.py..."
   # python3 Abstraction/main.py "$SUPERVISOR_TOKEN" "$Consumer_asset_IDs" "$Generator_asset_IDs" "$Energy_Source_asset_IDs" "$Building_consumption_IDs" "$Building_generation_IDs" &
# else
   # echo "El fitxer de configuració no existeix: $config_file"
# fi


echo "Starting server.py..."
python3 server.py


#!/usr/bin/with-contenv bashio

echo "Creem la carpeta (/share/exitos/) si no existeix, aqui guardarem fitxers persistents."
mkdir -p /share/exitos/

# Exportar configuració d'Ollama des de les opcions
export OLLAMA_URL=$(bashio::config 'ollama_url')
export OLLAMA_MODEL=$(bashio::config 'ollama_model')

echo "Starting server.py..."
python3 server.py


import requests
import os
import sha3
import base64
from eth_keys.main import PrivateKey

class Blockchain:
    def __init__(self):
        self.running_in_ha = "HASSIO_TOKEN" in os.environ
        self.base_url = "http://magiinterface.udg.edu:3000"


    def generar_claves_ethereum(self, semilla_texto: str) -> dict:
        k = sha3.keccak_256()
        k.update(semilla_texto.encode('utf-8'))
        pk = PrivateKey(k.digest())
        address = pk.public_key.to_checksum_address()
        return {"private_key": pk.to_hex(), "public_key": address }

    def get_login_hash_and_sign(self, public_address: str, private_key: str, message: str) -> dict:
        try:
            login_url = f"{self.base_url}/login?address={public_address}&message={message}"
            response_login = requests.get(login_url)
            response_login.raise_for_status()
            login_data = response_login.json()
            encoded_message = login_data.get("encodedMessage")
            hash_del_servidor = login_data.get("hash")
            if not encoded_message or not hash_del_servidor:
                return {"success": False, "error": "La respuesta de /login no contenía 'encodedMessage' o 'hash'."}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Error en la petición a /login: {e}"}

        message_bytes = hash_del_servidor.encode('utf-8')
        prefix = b"\x19Ethereum Signed Message:\n"
        message_len = str(len(message_bytes)).encode('utf-8')
        message_a_hashear = prefix + message_len + message_bytes
        k = sha3.keccak_256()
        k.update(message_a_hashear)
        hash_final_a_firmar = k.digest()
        if private_key.startswith('0x'):
            pk_bytes = bytes.fromhex(private_key[2:])
        else:
            pk_bytes = bytes.fromhex(private_key)
        pk = PrivateKey(pk_bytes)
        firma = pk.sign_msg_hash(hash_final_a_firmar)
        firma_hex = firma.to_hex()
        return {
                "encoded_message": encoded_message,
                "firma_hex": firma_hex
            }

    def registrar_usuario(self, public_address: str, private_key: str) -> dict:
        login_data = self.get_login_hash_and_sign(public_address, private_key, "addAddress")

        credenciales = f"{login_data.get('encoded_message')}:{login_data.get('firma_hex')}"
        credenciales_bytes = credenciales.encode("utf-8")
        credenciales_base64 = base64.b64encode(credenciales_bytes).decode("utf-8")
        add_user_url = f"{self.base_url}/userVerified/add-user"
        headers = { "Content-Type": "application/json", "Authorization": f"Basic {credenciales_base64}" }
        data = { "userAddress": public_address }
        try:
            response_add_user = requests.post(add_user_url, headers=headers, json=data)
            response_add_user.raise_for_status()
            return {
                "success": True,
                "status_code": response_add_user.status_code,
                "response": response_add_user.json()
            }
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                status_code = e.response.status_code
                try:
                    error_details = e.response.json()
                except requests.exceptions.JSONDecodeError:
                    error_details = e.response.text
                return {
                    "success": False,
                    "error": "Error HTTP del servidor en la petición a /certify.",
                    "status_code": status_code,
                    "details": error_details
                }
            else:
                return {
                    "success": False,
                    "error": "Error de conexión o de red.",
                "details": str(e) # Damos el texto del error de red para depuración.
            }

    def certify_string(self, public_address: str, private_key: str, message: str) -> dict:
        login_data = self.get_login_hash_and_sign(public_address, private_key, message)

        credenciales = f"{login_data.get('encoded_message')}:{login_data.get('firma_hex')}"
        credenciales_bytes = credenciales.encode("utf-8")
        credenciales_base64 = base64.b64encode(credenciales_bytes).decode("utf-8")

        certify_url = f"{self.base_url}/certificationVerified/certify"
        headers = { "Content-Type": "application/json", "Authorization": f"Basic {credenciales_base64}" }
        data = { "certifiedString": message, "description": message }
        try:
            response_certify = requests.post(certify_url, headers=headers, json=data)
            response_certify.raise_for_status()
            return {
                "success": True,
                "status_code": response_certify.status_code,
                "response": response_certify.json()
            }
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                status_code = e.response.status_code
                try:
                    error_details = e.response.json()
                except requests.exceptions.JSONDecodeError:
                    error_details = e.response.text
                return {
                    "success": False,
                    "error": "Error HTTP del servidor en la petición a /certify.",
                    "status_code": status_code,
                    "details": error_details
                }
            else:
                return {
                    "success": False,
                    "error": "Error de conexión o de red.",
                "details": str(e) # Damos el texto del error de red para depuración.
            }
import json
import traceback
import requests
import os
from bottle import template, request, response, request as bottle_request

# Global logger from parent (will be set in init_routes or imported if available)
logger = None

class LLMEngine:
    """
    Class to handle communication with the local Ollama LLM with conversation history.
    """
    def __init__(self, model="llama3.1:latest", api_url=None):
        self.model = model
        # Use environment variable if set, otherwise default to localhost (works with network_mode: host)
        if api_url is None:
            api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/chat")
        self.api_url = api_url
        self.system_prompt = (
            "Ets un expert en gestió energètica de la plataforma eXiT. "
            "La teva missió és ajudar l'usuari a entendre la seva configuració d'autoconsum, "
            "optimització de bateries i generació solar. Respon de manera amable, clara i professional, "
            "preferiblement en català. Si l'usuari no coneix el tema, explica els conceptes de manera senzilla."
        )
        # Diccionari per guardar l'historial de cada sessió (per session_id)
        self.conversations = {}

    def get_response(self, user_input, session_id="default"):
        """
        Obté resposta del LLM mantenint l'historial de conversa per sessió.
        """
        try:
            # Inicialitzar conversa si no existeix
            if session_id not in self.conversations:
                self.conversations[session_id] = [
                    {"role": "system", "content": self.system_prompt}
                ]
            
            # Afegir missatge de l'usuari
            self.conversations[session_id].append({
                "role": "user", 
                "content": user_input
            })
            
            payload = {
                "model": self.model,
                "messages": self.conversations[session_id],
                "stream": False
            }
            
            if logger:
                logger.info(f"🤖 Enviant petició a Ollama: {self.api_url}")
            
            res = requests.post(self.api_url, json=payload, timeout=60)
            res.raise_for_status()
            
            data = res.json()
            assistant_message = data.get("message", {}).get("content", "No he rebut cap resposta vàlida del model.")
            
            # Afegir resposta de l'assistent a l'historial
            self.conversations[session_id].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except requests.exceptions.ConnectionError as e:
            if logger: 
                logger.error(f"❌ Error de connexió amb Ollama a {self.api_url}: {e}")
            return f"Ho sento, no puc connectar amb Ollama a {self.api_url}. Assegura't que Ollama està executant-se al host."
        except requests.exceptions.HTTPError as e:
            if logger: 
                logger.error(f"❌ Error HTTP {e.response.status_code} de Ollama: {e}")
            return f"Error HTTP {e.response.status_code}: {e.response.text if hasattr(e.response, 'text') else str(e)}"
        except requests.exceptions.RequestException as e:
            if logger: 
                logger.error(f"❌ Error connectant amb Ollama: {e}")
            return "Ho sento, no puc connectar amb el motor d'IA local. Certifica que Ollama està funcionant."
        except Exception as e:
            if logger: 
                logger.error(f"❌ Error inesperat al LLM: {e}")
                logger.error(traceback.format_exc())
            return "Hi ha hagut un error inesperat processant la teva consulta."
    
    def clear_conversation(self, session_id="default"):
        """
        Esborra l'historial de conversa d'una sessió.
        """
        if session_id in self.conversations:
            self.conversations[session_id] = [
                {"role": "system", "content": self.system_prompt}
            ]
            return True
        return False

# Instància global
llm_engine = LLMEngine()

def init_routes(app, external_logger):
    global logger
    logger = external_logger
    
    @app.route('/llmChat')
    def llm_chat_page():
        return template('./www/llmChat.html')

    @app.route('/llm_response', method='POST')
    def llm_response():
        try:
            data = request.json
            if not data:
                response.status = 400
                return json.dumps({'status': 'error', 'message': 'Dades buides'})
            
            user_message = data.get('message', '')
            if not user_message:
                return json.dumps({'status': 'error', 'message': 'El missatge està buit'})
            
            # Obtenir session_id (pots usar IP, cookie o generar un ID únic)
            session_id = bottle_request.environ.get('REMOTE_ADDR', 'default')
            
            # Cridem el LLM amb historial
            response_text = llm_engine.get_response(user_message, session_id)
            
            return json.dumps({
                'status': 'ok',
                'response': response_text
            })
            
        except Exception as e:
            if logger:
                logger.error(f"❌ Error en LLM response: {e}")
                logger.error(traceback.format_exc())
            return json.dumps({
                'status': 'error', 
                'message': 'Ho sento, hi ha hagut un error sol·licitant la resposta.'
            })
    
    @app.route('/llm_clear', method='POST')
    def llm_clear():
        """
        Endpoint per esborrar l'historial de conversa.
        """
        try:
            session_id = bottle_request.environ.get('REMOTE_ADDR', 'default')
            llm_engine.clear_conversation(session_id)
            return json.dumps({'status': 'ok', 'message': 'Conversa esborrada'})
        except Exception as e:
            if logger: logger.error(f" Error esborrant conversa: {e}")
            return json.dumps({'status': 'error', 'message': 'Error esborrant conversa'})

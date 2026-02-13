import json
import traceback
import requests
import os
from bottle import template, request, response, request as bottle_request

# Global logger from parent (will be set in init_routes or imported if available)
logger = None

class LLMEngine:
    """
    Class to handle communication with Ollama LLM with conversation history.
    """
    def __init__(self, model=None, ollama_url=None):
        # Get model from environment variable or use default
        if model is None:
            model = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
        self.model = model
        # Get Ollama URL from environment variable or use default
        # Amb network_mode: host, localhost funciona directament
        if ollama_url is None:
            ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        # Assegurar que la URL base no té /api/chat al final
        self.ollama_base_url = ollama_url.rstrip('/')
        self.api_url = f"{self.ollama_base_url}/api/chat"
        self.system_prompt = (
            "Ets un expert en gestió energètica de la plataforma eXiT. "
            "La teva missió és ajudar l'usuari a entendre la seva configuració d'autoconsum, "
            "optimització de bateries i generació solar. Respon de manera amable, clara i professional, "
            "preferiblement en català. Si l'usuari no coneix el tema, explica els conceptes de manera senzilla."
        )
        # Diccionari per guardar l'historial de cada sessió (per session_id)
        self.conversations = {}
        
        if logger:
            logger.info(f"🔧 LLMEngine inicialitzat:")
            logger.info(f"   - Model: {self.model}")
            logger.info(f"   - URL base: {self.ollama_base_url}")
            logger.info(f"   - API endpoint: {self.api_url}")

    def get_response(self, user_input, session_id="default"):
        """
        Obté resposta d'Ollama mantenint l'historial de conversa per sessió.
        """
        try:
            if logger:
                logger.info(f"📨 Nova petició LLM per sessió: {session_id}")
                logger.info(f"   - Missatge usuari: {user_input[:50]}...")
            
            # Inicialitzar conversa si no existeix
            if session_id not in self.conversations:
                self.conversations[session_id] = [
                    {"role": "system", "content": self.system_prompt}
                ]
                if logger:
                    logger.info(f"   - Nova sessió creada amb system prompt")
            
            # Afegir missatge de l'usuari
            self.conversations[session_id].append({
                "role": "user", 
                "content": user_input
            })
            
            # Preparar payload per Ollama API
            payload = {
                "model": self.model,
                "messages": self.conversations[session_id],
                "stream": False
            }
            
            if logger:
                logger.info(f"🤖 Enviant petició a Ollama:")
                logger.info(f"   - URL: {self.api_url}")
                logger.info(f"   - Model: {self.model}")
                logger.info(f"   - Nombre de missatges a l'historial: {len(self.conversations[session_id])}")
                logger.info(f"   - Payload: {json.dumps(payload, indent=2, ensure_ascii=False)[:500]}...")
            
            res = requests.post(self.api_url, json=payload, timeout=120)
            
            if logger:
                logger.info(f"📡 Resposta rebuda:")
                logger.info(f"   - Status code: {res.status_code}")
                logger.info(f"   - Headers: {dict(res.headers)}")
                logger.info(f"   - Response text (primeres 200 chars): {res.text[:200]}")
            
            res.raise_for_status()
            
            data = res.json()
            if logger:
                logger.info(f"   - Response JSON keys: {list(data.keys())}")
            
            # Ollama /api/chat retorna la resposta en data["message"]["content"]
            assistant_message = data.get("message", {}).get("content", "No he rebut cap resposta vàlida del model.")
            
            if logger:
                logger.info(f"✅ Resposta processada correctament: {assistant_message[:100]}...")
            
            # Afegir resposta de l'assistent a l'historial
            self.conversations[session_id].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except requests.exceptions.ConnectionError as e:
            if logger: 
                logger.error(f"❌ Error de connexió amb Ollama a {self.api_url}: {e}")
                logger.error(f"   - Detalls: {traceback.format_exc()}")
            return f"❌ No puc connectar amb Ollama a {self.ollama_base_url}. Verifica que Ollama està executant-se i que la URL és correcta."
        except requests.exceptions.HTTPError as e:
            if logger: 
                logger.error(f"❌ Error HTTP {e.response.status_code} d'Ollama: {e}")
                logger.error(f"   - URL: {self.api_url}")
                logger.error(f"   - Response text: {e.response.text}")
                logger.error(f"   - Detalls: {traceback.format_exc()}")
            if e.response.status_code == 404:
                return f"❌ Model '{self.model}' no trobat. Assegura't que el model està descarregat a Ollama."
            elif e.response.status_code == 405:
                return f"❌ Error 405: Endpoint incorrecte. Verifica que Ollama està actualitzat i suporta /api/chat"
            else:
                return f"Error HTTP {e.response.status_code}: {e.response.text if hasattr(e.response, 'text') else str(e)}"
        except requests.exceptions.Timeout:
            if logger:
                logger.error(f"❌ Timeout esperant resposta d'Ollama")
            return "⏱️ El servidor Ollama està trigant massa. Pot ser que el model sigui massa gran o el servidor estigui ocupat."
        except requests.exceptions.RequestException as e:
            if logger: 
                logger.error(f"❌ Error connectant amb Ollama: {e}")
                logger.error(f"   - Detalls: {traceback.format_exc()}")
            return "Ho sento, no puc connectar amb el servidor Ollama. Verifica la configuració."
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

import json
import traceback
import requests
import os
from bottle import template, request, response, request as bottle_request

# Global logger from parent (will be set in init_routes or imported if available)
logger = None

class LLMEngine:
    """
    Class to handle communication with Ollama LLM with conversation history and tools.
    """
    def __init__(self, model=None, ollama_url=None):
        # Ollama Configuration (Hardcoded perque vull)
        self.model = "llama3.1:latest"
        self.ollama_base_url = "http://192.168.191.70:11434"
        
        self.api_url = f"{self.ollama_base_url}/api/chat"
        self.headers = {"Content-Type": "application/json"}

        self.system_prompt = (
            "Ets un expert en gestió energètica de la plataforma eXiT. "
            "La teva missió és ajudar l'usuari a entendre la seva configuració d'autoconsum, "
            "optimització de bateries i generació solar. Respon de manera amable, clara i professional, "
            "preferiblement en català (si detectes un altre idioma pots canviar). Si l'usuari no coneix el tema, explica els conceptes de manera senzilla.\n\n"
            "Quan l'usuari et demani una recomanació de configuració d'optimització:\n"
            "1. Utilitza l'eina 'get_available_device_types' per veure quins tipus de dispositius existeixen "
            "i quins paràmetres cal configurar per a cadascun. També tens l'eina 'get_current_day' i 'get_current_year' per saber la data actual.\n"
            "2. Opcionalment, utilitza 'get_optimization_configs' per veure les configuracions actuals de l'usuari.\n"
            "3. Basant-te en la situació que t'explica l'usuari (tipus de dispositiu que té, necessitats energètiques, etc.), "
            "recomana quin tipus de dispositiu escollir i quins valors posar a cada paràmetre.\n"
            "4. Explica SEMPRE el raonament darrere de cada decisió: per què has escollit aquell tipus, "
            "per què proposes aquells valors concrets per a les restriccions, i com afectarà a l'optimització energètica.\n"
            "5. Si no tens prou informació per fer una recomanació precisa, pregunta a l'usuari "
            "les dades que necessites (capacitat del dispositiu, consum habitual, etc.).\n\n"
            "IMPORTANT sobre les eines (tools):\n"
            "- Si una eina NO té paràmetres definits (com 'get_current_time'), NO t'inventis arguments. Crida-la amb un objecte buit {}.\n"
            "- No afegeixis mai paràmetres que no estiguin definits en la definició de l'eina."
        )
        self.conversations = {}
        self.tools = {}

        if logger:
            logger.info(f"🔧 LLMEngine inicialitzat (OLLAMA):")
            logger.info(f"   - Model: {self.model}")
            logger.info(f"   - API URL: {self.api_url}")

    def register_tool(self, name, func, description, parameters):
        """
        Registra una nova eina que l'LLM pot utilitzar.
        """
        tool_definition = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }
        self.tools[name] = {
            "definition": tool_definition,
            "func": func
        }
        if logger:
            logger.info(f"🛠️ Eina registrada: {name}")

    def get_response(self, user_input, session_id="default"):
        """
        Obté resposta de l'Ollama executant eines si cal.
        """
        try:
            # Inicialitzar conversa
            if session_id not in self.conversations:
                self.conversations[session_id] = [
                    {"role": "system", "content": self.system_prompt}
                ]
            
            # Afegir missatge usuari
            self.conversations[session_id].append({
                "role": "user", 
                "content": user_input
            })
            
            # Bucle d'execució d'eines (màx 5 iteracions)
            for _ in range(5):
                available_tools = [t["definition"] for t in self.tools.values()] if self.tools else None
                
                payload = {
                    "model": self.model,
                    "messages": self.conversations[session_id],
                    "stream": False
                }
                
                # Afegir eines
                if available_tools:
                    payload["tools"] = available_tools

                if logger:
                    logger.info(f"🤖 Enviant petició a OLLAMA...")

                res = requests.post(self.api_url, headers=self.headers, json=payload, timeout=120)
                
                if res.status_code != 200:
                    error_msg = f"Error Ollama {res.status_code}: {res.text}"
                    if logger: logger.error(f"❌ {error_msg}")
                    return f"❌ {error_msg}"

                data = res.json()
                
                # Ollama endpoint /api/chat returns message at root
                response_message = data.get("message", {})

                content = response_message.get("content", "")
                tool_calls = response_message.get("tool_calls", [])
                
                # Afegim la resposta de l'assistent a l'historial
                self.conversations[session_id].append(response_message)
                
                # Si no hi ha eines, hem acabat
                if not tool_calls:
                    if logger: logger.info(f"✅ Resposta final: {content[:50]}...")
                    return content
                
                if logger: logger.info(f"🛠️ Executant {len(tool_calls)} eines...")
                
                # Executar eines
                for tool_call in tool_calls:
                    fn_name = tool_call["function"]["name"]
                    fn_args = tool_call["function"]["arguments"]
                    
                    if fn_name in self.tools:
                        if logger: logger.info(f"   ▶️ {fn_name}({fn_args})")
                        try:
                            # Robustesa: Si l'eina no té paràmetres definits, ignorem els que enviï l'LLM (hallucinations)
                            tool_def = self.tools[fn_name]["definition"]["function"]
                            has_params = bool(tool_def.get("parameters", {}).get("properties"))
                            
                            if not has_params:
                                result = self.tools[fn_name]["func"]()
                            else:
                                result = self.tools[fn_name]["func"](**fn_args)
                                
                            result_str = str(result)
                        except Exception as e:
                            result_str = f"Error: {e}"
                            if logger: logger.error(f"   ❌ Error: {e}")
                        
                        tool_msg = {
                            "role": "tool",
                            "content": result_str,
                            "name": fn_name
                        }
                        
                        self.conversations[session_id].append(tool_msg)

                    else:
                        self.conversations[session_id].append({
                            "role": "tool",
                            "content": f"Error: Tool {fn_name} not found",
                            "name": fn_name
                        })

            return "⚠️ Límit d'iteracions d'eines superat."

        except requests.exceptions.ConnectionError:
            return f"❌ Error de connexió amb Ollama. Verifica la URL."
        except Exception as e:
            if logger: logger.error(f"❌ Error inesperat: {e}\n{traceback.format_exc()}")
            return f"Error inesperat: {e}"
    
    def clear_conversation(self, session_id="default"):
        if session_id in self.conversations:
            self.conversations[session_id] = [
                {"role": "system", "content": self.system_prompt}
            ]
            return True
        return False


# Instància global
llm_engine = LLMEngine()


def _add_cors_headers():
    """Afegeix headers CORS a la resposta."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'


def init_routes(app, external_logger):
    global logger
    logger = external_logger

    # Hook global CORS: s'executa després de cada request
    @app.hook('after_request')
    def enable_cors():
        _add_cors_headers()

    @app.route('/llmChat')
    def llm_chat_page():
        return template('./www/llmChat.html')

    @app.route('/llm_response', method=['POST', 'OPTIONS'])
    def llm_response():
        # Resposta ràpida al preflight CORS
        if request.method == 'OPTIONS':
            return {}

        if logger:
            logger.info("🔵 Endpoint /llm_response cridat")
        try:
            data = request.json
            if logger:
                logger.info(f"   - Dades rebudes: {data}")
            
            if not data:
                response.status = 400
                return json.dumps({'status': 'error', 'message': 'Dades buides'})
            
            user_message = data.get('message', '')
            if not user_message:
                return json.dumps({'status': 'error', 'message': 'El missatge està buit'})
            
            session_id = bottle_request.environ.get('REMOTE_ADDR', 'default')
            
            response_text = llm_engine.get_response(user_message, session_id)
            
            response.content_type = 'application/json'
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

    @app.route('/llm_clear', method=['POST', 'OPTIONS'])
    def llm_clear():
        """
        Endpoint per esborrar l'historial de conversa.
        """
        if request.method == 'OPTIONS':
            return {}
        try:
            session_id = bottle_request.environ.get('REMOTE_ADDR', 'default')
            llm_engine.clear_conversation(session_id)
            return json.dumps({'status': 'ok', 'message': 'Conversa esborrada'})
        except Exception as e:
            if logger: logger.error(f" Error esborrant conversa: {e}")
            return json.dumps({'status': 'error', 'message': 'Error esborrant conversa'})

    @app.route('/llm_history', method=['GET', 'OPTIONS'])
    def llm_history():
        """
        Retorna l'historial de missatges de la sessió actual (sense missatges de sistema ni d'eines).
        """
        if request.method == 'OPTIONS':
            return {}
        try:
            session_id = bottle_request.environ.get('REMOTE_ADDR', 'default')
            conversation = llm_engine.conversations.get(session_id, [])

            # Filtrem: només retornem missatges de l'usuari i l'assistent, no system ni tool
            visible_messages = [
                {"role": msg["role"], "content": msg.get("content", "")}
                for msg in conversation
                if msg["role"] in ("user", "assistant") and msg.get("content", "").strip()
            ]

            response.content_type = 'application/json'
            return json.dumps({'status': 'ok', 'messages': visible_messages})
        except Exception as e:
            if logger: logger.error(f"Error recuperant historial: {e}")
            return json.dumps({'status': 'error', 'messages': []})


    @app.route('/llm_test', method='GET')
    def llm_test():
        if logger:
            logger.info("🧪 Test endpoint cridat")
        return json.dumps({
            'status': 'ok',
            'message': 'LLM routes are working!',
            'ollama_url': llm_engine.ollama_base_url,
            'model': llm_engine.model
        })

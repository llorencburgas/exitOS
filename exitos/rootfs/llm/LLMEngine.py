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
            "## Identitat i Rol\n"
            "Ets l'Assistent Intel·ligent de la plataforma eXiT (Energy Management System). "
            "Ets un expert en gestió energètica, autoconsum, bateries i sistemes fotovoltaics. "
            "La teva missió és ajudar l'usuari a optimitzar la seva llar o indústria per reduir costos i ser més eficient.\n\n"
            
            "## Directrius de Resposta\n"
            "- **Idioma**: Respon preferiblement en l'idioma que t'ha parlat l'usuari (Català, Castellà o Anglès).\n"
            "- **To**: Amable, clar, professional i didàctic.\n"
            "- **Raonament**: Pensa pas a pas (Chain of Thought). Explica sempre el *perquè* de les teves recomanacions.\n\n"
            
            "## Ús d'Eines (Tools)\n"
            "Tens accés a eines per consultar dades en temps real. Segueix aquest protocol:\n"
            "1. **Consulta abans de respondre**: Si l'usuari pregunta per dades específiques (preus, sensors, configuracions, o quins dispositius té), UTILITZA l'eina corresponent primer.\n"
            "2. **Seqüència de Recomanació**:\n"
            "   a. Crida `get_system_entities` per veure quins dispositius i entitats reals hi ha al sistema (Home Assistant). Allà trobaràs dispositius com 'Orphans', 'Backup', 'Consum', etc.\n"
            "   b. Crida `get_available_device_types` per conèixer els models i paràmetres teòrics de l'optimitzador.\n"
            "   c. Crida `get_optimization_configs` per verificar què té configurat l'usuari actualment.\n"
            "   d. Crida `get_sensor_value` si necessites l'estat actual d'alguna entitat específica.\n"
            "   e. Crida `get_current_day` i `get_current_year` per saber la data actual corresponent.\n"
            "3. **Robustesa**: NO t'inventis paràmetres. Si una eina no demana res, envia un objecte buit `{}`. Utilitza només els paràmetres definits a la documentació de cada tool.\n\n"
            
            "## Context de Recomanació d'Optimització\n"
            "Quan un usuari vulgui configurar o millorar una optimització:\n"
            "- Demana dades si falten (capacitat de bateria, potència inversor, etc.).\n"
            "- Proposa valors concrets per a les restriccions basant-te en els tipus de dispositius oficials de la plataforma.\n"
            "- Explica com cada canvi afectarà el balanç energètic (autoconsum, injecció a xarxa, estalvi).\n\n"
            "IMPORTANT: Ets un assistent tècnic de eXiT, no facis recomanacions que no estiguin suportades per la plataforma."
        )
        self.conversations = {}
        self.tools = {}

        if logger:
            logger.info(f"🔧 LLMEngine inicialitzat | Model: {self.model} | URL: {self.api_url}")

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
        pass  # Registre silenciós, eina afegida correctament

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
                    if logger: logger.info(f"💬 Resposta: {content[:80]}{'...' if len(content) > 80 else ''}")
                    return content
                
                # Executar eines
                for tool_call in tool_calls:
                    fn_name = tool_call["function"]["name"]
                    fn_args = tool_call["function"]["arguments"]
                    
                    if fn_name in self.tools:
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
        return json.dumps({
            'status': 'ok',
            'message': 'LLM routes are working!',
            'ollama_url': llm_engine.ollama_base_url,
            'model': llm_engine.model
        })

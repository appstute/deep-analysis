import os
import json
import logging
import asyncio

from openai import AsyncOpenAI
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from execution_layer.agents.coding_tool import JupyterExecutionTool
from agents.token_manager import check_token_limit_internal, complete_job_gracefully, TokenLimitExceededException

# load .env
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Updated system prompt with directory specifications and error handling
SYSTEM_PROMPT = """You are a Python data science assistant.
Convert the user's request into executable Python code.
Use the JSON list of previous runs (code + output) for context.

IMPORTANT: You must provide detailed business-focused thinking logs throughout your analysis process so users can see your business reasoning and strategic decision-making process. Think like a business analyst, not just a technical coder.

IMPORTANT RULES:
- Only return valid Python code
- Always use the input directory specified in state['input_dir'] for reading files (e.g., pd.read_pickle(os.path.join(state['input_dir'], '*.pkl')))
- The input directory is dynamically set per job to access job-specific data files 
- Always save plots, charts, outputs to the output directory specified in state['output_dir'] with descriptive names (e.g., plt.savefig(os.path.join(state['output_dir'], 'correlation_between_features.png')))
- The output directory is dynamically set per job to ensure outputs are saved in job-specific locations
- Import os module when saving files: import os  
- Example usage: 
  * For plots: plt.savefig(os.path.join(state['output_dir'], 'my_chart.png'))
  * For data: df.to_csv(os.path.join(state['output_dir'], 'processed_data.csv'))
  * For JSON: with open(os.path.join(state['output_dir'], 'results.json'), 'w') as f: json.dump(data, f)
- Reference existing variables or dataframes from previous executions
- Use plt.show() after plots for display
- For data exploration, make sure to output the result (use print() if needed
- Do not include explanations or markdown
- Make the last line an expression that shows the result

CRITICAL ERROR HANDLING:
- If previous code failed, analyze the error and generate corrected code
- Handle common errors like missing files, wrong column names, data type issues
- Use only standard libraries: pandas, numpy, matplotlib, seaborn, scipy, statsmodels
- If you see "ModuleNotFoundError" for a module, use os.system('pip install <module>') to install it
- For missing modules, find alternative approaches with available libraries

Response format (JSON):
{
    "thinking_logs": [
        "💼 Understanding business question behind the analysis request...",
        "📈 Planning approach to generate business-relevant insights...",
        "🎯 Selecting methods that will answer key business questions...",
        "💡 Implementing analysis to support business decisions...",
        "📊 Ensuring outputs are business-ready for stakeholders..."
    ],
    "code": "your executable Python code here"
}

Make sure to include 4-6 detailed thinking_logs that show your actual reasoning process.
"""

class CodeAgent(Runnable):
    def __init__(self):
        # spin up a persistent Jupyter kernel
        self.executor = JupyterExecutionTool()
        self.max_retries = 3
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("MODEL_NAME", "gpt-4.1-mini")

    async def nl_to_code(self, nl_command: str, history: list, retry_count: int = 0, state: dict = {}) -> str:
        # pass last 5 history items as context including errors
        ctx = json.dumps(history[-5:], indent=2) if history else "[]"
        
        retry_context = ""
        if retry_count > 0:
            retry_context = f"\nThis is retry attempt {retry_count}. Previous attempts failed. Analyze the errors in context and generate code to fix the issues."
            

        # Get dynamic paths from state or use defaults
        input_dir = state.get('input_dir', '/app/execution_layer/input_data')
        output_dir = state.get('output_dir', '/app/execution_layer/output_data')
        
        # Debug logging to verify paths
        print(f"🔧 [EXECUTOR] Using paths for code generation:")
        print(f"📥 Input dir: {input_dir}")
        print(f"📤 Output dir: {output_dir}")
        print(f"🆔 Job ID: {state.get('job_id', 'unknown')}")
        
        user_msg = f"""
        Context (last 5 runs, with errors if any):
        {ctx}

        User request:
        {nl_command}
        {retry_context}

        Generate Python code only. 
        CRITICAL: Use these specific paths:
        - For reading files: {input_dir}
        - For saving outputs: {output_dir}
        
        Example: plt.savefig(os.path.join('{output_dir}', 'my_chart.png'))
        """
        
        try:
            # Check token limit internally before making LLM call (MULTI-USER SAFE)
            can_proceed, token_message, should_complete = check_token_limit_internal(state, estimated_tokens=1000)
            
            if not can_proceed:
                if should_complete:
                    # Complete job gracefully instead of failing  
                    print(f"🔥 [EXECUTOR] {token_message}")
                    return complete_job_gracefully(state)
                else:
                    # Hard failure (insufficient tokens from start)
                    state["error"] = f"🚫 PROCESS STOPPED: {token_message}"
                    print(f"🚫 [EXECUTOR] {token_message}")
                    raise TokenLimitExceededException(token_message)
            
            print(f"📊 [EXECUTOR] {token_message}")
            
            resp = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ],
                text={
                    "format": {"type": "json_object"},
                    "verbosity": "medium"
                },
                max_output_tokens=2000
            )
            
            # Update metrics in state if available
            if state and "metrics" in state:
                state["metrics"]["prompt_tokens"] += getattr(resp.usage, "input_tokens", 0) if hasattr(resp, "usage") else 0
                state["metrics"]["completion_tokens"] += getattr(resp.usage, "output_tokens", 0) if hasattr(resp, "usage") else 0
                state["metrics"]["total_tokens"] += (
                    (getattr(resp.usage, "input_tokens", 0) + getattr(resp.usage, "output_tokens", 0)) if hasattr(resp, "usage") else 0
                )
                state["metrics"]["successful_requests"] += 1
            
            # Log token usage for this call
            if hasattr(resp, "usage") and resp.usage:
                tokens_used = getattr(resp.usage, "input_tokens", 0) + getattr(resp.usage, "output_tokens", 0)
                print(f"📊 [EXECUTOR] Used {tokens_used} tokens (Total so far: {state['metrics']['total_tokens']})")
            
            content = getattr(resp, "output_text", None)
            if not content:
                try:
                    content = resp.output[0].content[0].text
                except Exception:
                    content = "{}"
            
            try:
                result = json.loads(content)
                
                # Stream LLM thinking logs via progress_callback
                progress_callback = state.get("progress_callback", lambda *args, **kwargs: None)
                thinking_logs = result.get('thinking_logs', [])
                
                for i, log in enumerate(thinking_logs):
                    progress_callback(f"🤖 Code Gen #{i+1}", log, "⚙️")
                    # Small delay to make logs visible
                    await asyncio.sleep(0.2)
                
                code = result.get("code", "")
            except json.JSONDecodeError:
                # Fallback to original behavior if JSON parsing fails
                code = content
            
            # Clean up code formatting (for fallback cases)
            if code.startswith("```python"):
                code = code.split("```python")[1]
            if code.startswith("```"):
                code = code.split("```")[1]
            if code.endswith("```"):
                code = code[:-3]
            
            code = code.strip()
            # logger.info(f"Generated code (attempt {retry_count + 1}): {code}")
            return code
            
        except Exception as e:
            logger.error(f"Error generating code: {e}")
            return f"print('Error generating code: {str(e)}')"

    async def execute_with_retry(self, nl_command: str, history: list, state: dict = {}) -> dict:
        """Execute code with retry logic for error handling"""
        
        for attempt in range(self.max_retries):
            try:
                # Generate code
                code = await self.nl_to_code(nl_command, history, attempt, state)
                
                # Execute code
                logger.info(f"Executing code (attempt {attempt + 1}): {code}")
                result = self.executor.execute_code(code)
                logger.info(f"Execution result (attempt {attempt + 1}): {result}")
                
                # If successful, return result
                if result["success"] or not result["error"]:
                    return {
                        "code": code,
                        "output": result["output"],
                        "error": None,
                        "attempts": attempt + 1
                    }
                
                # If failed and not last attempt, add error to history for context
                if attempt < self.max_retries - 1:
                    error_entry = {
                        "code": code,
                        "output": result["output"],
                        "error": result["error"],
                        "attempt": attempt + 1
                    }
                    history.append(error_entry)
                    logger.warning(f"Attempt {attempt + 1} failed: {result['error']}. Retrying...")
                else:
                    # Last attempt failed
                    return {
                        "code": code,
                        "output": result["output"],
                        "error": result["error"],
                        "attempts": attempt + 1
                    }
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} exception: {e}")
                if attempt == self.max_retries - 1:
                    return {
                        "code": f"print('Failed after {self.max_retries} attempts')",
                        "output": "",
                        "error": str(e),
                        "attempts": attempt + 1
                    }
        
        # Should not reach here, but just in case
        return {
            "code": "",
            "output": "",
            "error": "Max retries exceeded",
            "attempts": self.max_retries
        }

    async def ainvoke(self, state: dict, config=None, **kwargs) -> dict:
        nl = state.get("command", "").strip()
        if not nl:
            state["error"] = "No 'command' found in state"
            return state

        # init history if missing
        history = state.setdefault("history", [])

        try:
            # Execute with retry logic
            logger.info(f"Processing command: {nl}")
            result = await self.execute_with_retry(nl, history.copy(), state)  # Pass state for metrics tracking

            # Append successful result to history
            entry = {
                "code": result["code"],
                "output": result["output"],
                "error": result["error"],
                "attempts": result.get("attempts", 1)
            }
            history.append(entry)

            # Update state
            state.update({
                "last_code": result["code"],
                "last_output": result["output"],
                "last_error": result["error"],
                "history": history,
                "error": None
            })
            
            if result["error"]:
                logger.warning(f"Final execution failed after {result.get('attempts', 1)} attempts: {result['error']}")
            else:
                logger.info(f"Execution successful after {result.get('attempts', 1)} attempts")
            
        except Exception as e:
            logger.error(f"CodeAgent error: {e}")
            state["error"] = str(e)

        return state

    def invoke(self, state: dict, config=None, **kwargs):
        # sync wrapper
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return asyncio.create_task(self.ainvoke(state, config, **kwargs))
            else:
                return asyncio.run(self.ainvoke(state, config, **kwargs))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.ainvoke(state, config, **kwargs))

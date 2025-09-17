import os
import json
import logging
import asyncio
from typing import Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from agents.eda_agent import EDAAgent
from agents.hypothesis_agent import HypothesisAgent
from agents.narrator_agent import NarratorAgent
from agents.token_manager import check_token_limit_internal, complete_job_gracefully, TokenLimitExceededException

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Domain directory will be loaded dynamically per job
def load_domain_directory(input_dir: str = '/app/execution_layer/input_data') -> dict:
    """Load domain directory from dynamic input path"""
    domain_path = os.path.join(input_dir, 'domain_directory.json')
    if os.path.exists(domain_path):
        try:
            with open(domain_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading domain directory from {domain_path}: {e}")
    else:
        logger.warning(f"Domain directory not found at {domain_path}")
    return {}

def create_query_analysis_prompt(domain_directory: dict) -> str:
    """Create query analysis prompt with dynamic domain directory"""
    return f"""You are an expert query analyst who understands user queries and have domain knowledge.
Domain Directory: {domain_directory}

IMPORTANT: You must provide detailed business-focused thinking logs throughout your analysis process so users can see your business reasoning and decision-making process. Think like a business analyst, not a technical analyst.

Step-by-step business analysis process with thinking logs:
Step 1: Analyze the user query and use your domain knowledge to determine the intent(What user wants)
Step 2: Use the intent and break down the complex query into sub queries
Step 3: Determine the brief and exact plan to solve the sub queries(include required dimensions and facts)
Step 4: Determine the appropriate output like types of graphs, charts, tables, etc. 

Response format (JSON):
{{
    "thinking_logs": [
        "💼 Understanding business question and stakeholder needs...",
        "🏢 Identifying relevant business entities and KPIs: [specific business areas]",
        "🎯 Defining business objective: [what decision will this inform]",
        "📋 Breaking down into business sub-questions: [specific business queries]",
        "💡 Planning analysis approach to drive business insights: [business strategy]",
        "📊 Selecting business-relevant outputs: [executive dashboards/reports]"
    ],
    "user_intent": "brief description of what user wants",
    "sub_queries": "list of sub queries",
    "plan": "brief plan to solve the sub queries(what to use to solve, what dimensions and facts to use) [{{"sub_query1":"plan1", "sub_query2":"plan2",...}}]",
    "expected_output": "list of output and it's brief description of expected output"
}}

Make sure to include 4-6 detailed thinking_logs that show your actual reasoning process, not generic statements.
"""

class DataAnalysisAgent(Runnable):
    def __init__(self, output_dir):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("MODEL_NAME", "gpt-4.1-mini")
        self.output_dir = output_dir
        print("output_dir in DataAnalysisAgent", self.output_dir)

    async def analyze_user_query(self, user_query: str, state: dict) -> Dict[str, Any]:
        """Analyze user query to determine analysis approach"""
        try:
            logger.info(f"Processing user query: {user_query}")
            
            # Load domain directory dynamically from job-specific input directory
            input_dir = state.get('input_dir', '/app/execution_layer/input_data')
            domain_directory = load_domain_directory(input_dir)
            
            print(f"🔧 [DATA ANALYSIS AGENT] Using input dir: {input_dir}")
            print(f"📁 [DATA ANALYSIS AGENT] Domain directory loaded: {len(domain_directory)} entries")
            
            # Create dynamic prompt with job-specific domain directory
            query_analysis_prompt = create_query_analysis_prompt(domain_directory)
            
            # Check token limit internally before making LLM call (MULTI-USER SAFE)
            can_proceed, token_message, should_complete = check_token_limit_internal(state, estimated_tokens=800)
            
            if not can_proceed:
                if should_complete:
                    # Complete job gracefully instead of failing
                    print(f"🔥 [DATA_ANALYSIS_AGENT] {token_message}")
                    return complete_job_gracefully(state)
                else:
                    # Hard failure (insufficient tokens from start)
                    state["error"] = f"🚫 PROCESS STOPPED: {token_message}"
                    print(f"🚫 [DATA_ANALYSIS_AGENT] {token_message}")
                    raise TokenLimitExceededException(token_message)
            
            print(f"📊 [DATA_ANALYSIS_AGENT] {token_message}")
            
            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": query_analysis_prompt},
                    {"role": "user", "content": f"User query: {user_query}"}
                ],
                text={
                    "format": {"type": "json_object"},
                    "verbosity": "medium"
                },
                max_output_tokens=1000
            )
            
            # Update metrics in state
            state["metrics"]["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
            state["metrics"]["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
            state["metrics"]["total_tokens"] += (
                getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
            )
            state["metrics"]["successful_requests"] += 1
            
            # Log token usage for this call
            if hasattr(response, "usage") and response.usage:
                tokens_used = getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                print(f"📊 [DATA_ANALYSIS_AGENT] Used {tokens_used} tokens (Total so far: {state['metrics']['total_tokens']})")
            
            content = getattr(response, "output_text", None)
            if not content:
                try:
                    content = response.output[0].content[0].text
                except Exception:
                    content = "{}"
            
            result = json.loads(content)
            
            # Stream LLM thinking logs via progress_callback
            progress_callback = state.get("progress_callback", lambda *args, **kwargs: None)
            thinking_logs = result.get('thinking_logs', [])
            
            for i, log in enumerate(thinking_logs):
                progress_callback(f"🤖 LLM Thinking #{i+1}", log, "🧠")
                # Small delay to make logs visible
                await asyncio.sleep(0.2)
            
            logger.info(f"Query analysis complete: {result.get('user_intent', '')}")
            return result
        except Exception as e:
            logger.error(f"Error analyzing user query: {e}")
            return self._fallback_query_analysis(user_query)

    def _fallback_query_analysis(self, user_query: str) -> Dict[str, Any]:
        """Fallback analysis if JSON parsing fails"""
        return {
            "user_intent": "Analyze the dataset and solve the user query",
            "sub_queries": ["Analyze dataset", "Identify related columns and datasets", "Generate output based on analysis"],
            "plan": [{"Analyze dataset":"Use EDA techniques to explore dataset"}, {"Identify related columns and datasets":"Identify key relationships and patterns"}, {"Generate output based on analysis":"Generate visualizations and summary statistics"}],
            "expected_output": "Charts, graphs, and summary statistics based on the dataset",
        }
        
    async def ainvoke(self, state: dict, config=None, **kwargs) -> dict:
        """Main data analysis agent logic - orchestrates the entire pipeline"""
        
        try:
            original_query = state["original_query"]
            
            # Get progress callback from state (passed from execution_api.py)
            progress_callback = state.get("progress_callback", lambda *args, **kwargs: None)
            
            # Step 1: Analyze user query
            logger.info("Analyzing user query...")
            progress_callback("Query Analysis", "Understanding your question and creating analysis plan", "🧠")
            
            query_analysis = await self.analyze_user_query(original_query, state)
            state["query_analysis"] = query_analysis
            logger.info(f"Query analysis result: {query_analysis}")
            logger.info("Query analysis complete")
            
            # Step 2: Run EDA with determined user intent
            logger.info(f"Running EDA with intent: {query_analysis['user_intent']}")
            progress_callback("EDA Started", "Starting exploratory data analysis", "📊")
            
            eda_agent = EDAAgent(output_dir=self.output_dir)
            # Set EDA analysis type and run on the same shared state
            state["command"] = f"Perform {query_analysis} analysis: {original_query}"
            
            progress_callback("EDA In Progress", "Analyzing data patterns and distributions", "🔍")
            state = await eda_agent.ainvoke(state, config, **kwargs)
            
            print("="*60)
            logger.info(f"eda_summary in data analysis: {state['eda_summary']}")
            print("="*100)
            # EDAAgent already updated the shared state
            
            # Step 3: Pass to Hypothesis Agent
            logger.info("Passing to Hypothesis Agent...")
            progress_callback("Hypothesis Testing", "Testing statistical hypotheses and insights", "🔬")
            
            hypothesis_agent = HypothesisAgent(output_dir=self.output_dir)
            state["query_analysis"] = query_analysis
            state = await hypothesis_agent.ainvoke(state, config, **kwargs)

            print("="*100)
            logger.info(f"Hypothesis Findings: {state['hypothesis_findings']}")
            print("="*100)

            # # # Update state with hypothesis results
            print("="*100)
            logger.info(f"Hypothesis Summary: {state['hypothesis_summary']}")
            print("="*100)
            
            # Step 4: Pass to Narrator Agent
            logger.info("Passing to Narrator Agent...")
            progress_callback("Story Generation", "Creating narrative insights from analysis", "📖")
            
            narrator_agent = NarratorAgent(output_dir=self.output_dir)
            state = await narrator_agent.ainvoke(state, config, **kwargs)
            
            # Step 5: Final report generation
            progress_callback("Report Generation", "Generating comprehensive analysis report", "📋")
            
            state["error"] = state.get("error")
            logger.info("Data Analysis pipeline completed successfully")
            
            # Final completion
            progress_callback("Analysis Complete", "Analysis completed successfully! 🎉", "✅")
            
        except Exception as e:
            # Emit error progress
            progress_callback = state.get("progress_callback", lambda *args, **kwargs: None)
            progress_callback("Analysis Failed", f"Something went wrong", "❌")
            
            logger.error(f"Data Analysis Agent error: {e}")
            state["error"] = f"Data Analysis Agent failed: {str(e)}"
            
        return state

    def invoke(self, state: dict, config=None, **kwargs):        
        """Synchronous wrapper"""
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
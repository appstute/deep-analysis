import os
import json
import logging
import asyncio
import re
import base64
from typing import List, Dict, Any
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from agents.executor import CodeAgent
from agents.token_manager import check_token_limit_internal, TokenLimitExceededException

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EDA_SYSTEM_PROMPT = """You are an expert data science EDA (Exploratory Data Analysis) coordinator.
Break down user requests into 3-5 lightweight, executable subtasks for data analysis.

IMPORTANT: You must provide detailed business-focused thinking logs throughout your analysis process so users can see your business reasoning and strategic decision-making process. Think like a business analyst, not a technical analyst.
 
Instructions:
- Analyze the user's intent.
- Determine appropriate outputs (graphs, charts, tables, etc.).
- Select simple graphs/charts that are easy to interpret like bar charts, line graphs, pie charts, heatmaps, etc.
- For each visualization, include correct dimensions and facts so results are easy to understand.
- Add proper legends, axis labels, and titles for clarity.
- For each graph/chart/table, include a brief statement of what it shows, how it was created, and why it is relevant; incorporate this brief explanation into the visualization as legends.
- Break the request into small, focused subtasks. Each task should be quick to execute and produce clear output.
 
Response format (JSON):
{
    "thinking_logs": [
        "💼 Understanding business problem and decision-making needs...",
        "📈 Identifying key business metrics and performance indicators...",
        "🎯 Focusing on insights that will impact business strategy...",
        "📋 Planning business-relevant analysis steps...",
        "💡 Designing visualizations for executive decision-making..."
    ],
    "tasks": [
        {
            "task_id": 1,
            "description": "read domain_directory.json and print it",
            "code_instruction": "Read the domain_directory.json file and print it."
        },
        {
            "task_id": 2,
            "description": "Load dataset",
            "code_instruction": "Load the dataset from the input_data directory based on user request."
        }
    ]
}
 
Additional requirements:
- First task: read domain_directory.json and understand the dataset.
- Check input_data directory for available datasets and their column names.
- Save generated files using the dynamic output_dir path with appropriate names.
- Perform basic data cleaning and cleansing if needed.
 
Important:
First two tasks should be to read the domain_directory.json and load the dataset and then refer plan from query_analysis['plan'].
Make sure to include 4-6 detailed thinking_logs that show your actual reasoning process.
"""

ANALYSIS_SYSTEM_PROMPT = """You are an expert data analyst reviewing EDA task outputs.
Based on the completed EDA tasks and their outputs, determine if more analysis is needed.

You will receive:
- List of completed tasks with their outputs
- Current analysis goal

Respond with JSON:
{
    "sufficient": true/false,
    "reasoning": "explanation of why analysis is sufficient or not",
    "additional_tasks": [
        {
            "task_id": X,
            "description": "task description",
            "code_instruction": "specific instruction"
        }
    ]
}

If sufficient=true, additional_tasks should be empty."""

VISION_SYSTEM_PROMPT = """You are an expert data visualization analyst with the ability to interpret charts, graphs, and visual data representations.

Your role is to analyze generated visualizations and provide insights about:
- Chart types and their appropriateness for the data
- Patterns, trends, and anomalies visible in the visualizations
- Data distribution characteristics
- Relationships between variables
- Outliers and notable data points
- Statistical insights that can be derived from the visual patterns
- Quality and clarity of the visualizations

For each image, provide:
1. Description of what the visualization shows
2. Key insights and patterns observed
3. Statistical or analytical conclusions
4. Any recommendations for further analysis

Be concise but thorough in your analysis. Focus on actionable insights that complement the numerical analysis."""

SYNTHESIS_SYSTEM_PROMPT = """You are an expert data analyst creating concise EDA summaries.
Based on the EDA task outputs, create a brief, insightful summary.

Focus on:
- Key findings and patterns
- Data quality observations
- Statistical insights
- Notable correlations or anomalies

Keep the summary concise but informative. Structure with clear sections."""

class EDAAgent(Runnable):
    def __init__(self, output_dir):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("MODEL_NAME", "gpt-4.1-mini")
        self.state = None
        self.output_dir = output_dir
        self.max_iterations = 3  # Prevent infinite loops

    def encode_image_to_base64(self, image_path: str):
        """Encode image to base64 for Vision API"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image {image_path}: {e}")
            return None

    async def analyze_images(self, state: dict) -> str:
        """Analyze generated images using Vision API and create combined report"""
        
        # Look for images in the execution_layer/output_data/ directory
        # Ensure we have a Path object so .exists() and .glob() work correctly
        # from pathlib import Path  # local import to avoid any missing import issues in other contexts
        eda_output_dir = Path(self.output_dir)
        image_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.pdf']
        
        found_images = []
        if eda_output_dir.exists():
            for ext in image_extensions:
                found_images.extend(list(eda_output_dir.glob(f"*{ext}")))
        
        # Remove duplicates
        found_images = list(set(found_images))
        
        if not found_images:
            logger.info("No images found for vision analysis")
            return "No visualizations were generated during the analysis."
        
        logger.info(f"Found {len(found_images)} images for vision analysis")
        
        vision_analyses = []
        
        for img_path in found_images:
            try:
                # Only analyze common image formats that Vision API can handle
                if img_path.suffix.lower() not in ['.png', '.jpg', '.jpeg']:
                    continue
                    
                base64_image = self.encode_image_to_base64(str(img_path))
                if not base64_image:
                    continue
                
                vision_msg = f"""
Analyze this data visualization image generated by the EDA process: {img_path.name}

Please provide:
1. Description of the chart/graph type and what it shows
2. Key patterns, trends, or insights visible
3. Statistical observations
4. Any notable findings or anomalies
5. How this visualization contributes to understanding the data

Be concise but thorough in your analysis.
"""

                # Check token limit internally before making LLM call (MULTI-USER SAFE)
                can_proceed, token_message = check_token_limit_internal(state, estimated_tokens=600)
                
                if not can_proceed:
                    state["error"] = f"🚫 PROCESS STOPPED: {token_message}"
                    print(f"🚫 [EDA_AGENT] {token_message}")
                    raise TokenLimitExceededException(token_message)
                
                print(f"📊 [EDA_AGENT] {token_message}")

                response = await self.client.responses.create(
                    model=self.model,
                    input=[
                        {"role": "system", "content": VISION_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": vision_msg},
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/{img_path.suffix[1:]};base64,{base64_image}"
                                }
                            ]
                        }
                    ],
                    max_output_tokens=600
                )
                
                # Update metrics in state (existing functionality - keep as is)
                state["metrics"]["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
                state["metrics"]["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
                state["metrics"]["total_tokens"] += (
                    getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                )
                state["metrics"]["successful_requests"] += 1
                
                analysis = getattr(response, "output_text", None)
                if not analysis:
                    try:
                        analysis = response.output[0].content[0].text
                    except Exception:
                        analysis = ""
                vision_analyses.append(f"**{img_path.name}:**\n{analysis}")
            
            except Exception as e:
                logger.error(f"Error analyzing image {img_path}: {e}")
                vision_analyses.append(f"**{img_path.name}:** Error analyzing image - {str(e)}")
        
        if vision_analyses:
            combined_report = "## Visual Analysis Report\n\n" + "\n\n".join(vision_analyses)
            logger.info("Vision analysis completed successfully")
            return combined_report
        else:
            return "## Visual Analysis Report\n\nNo images could be analyzed."

    def _safe_json(self, content: str, fallback: dict) -> dict:
            """Safely parse JSON returned by the LLM, returning fallback if parsing fails."""
            try:
                return json.loads(content)
            except Exception:
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group())
                    except Exception:
                        pass
            return fallback


    async def plan_initial_tasks(self, user_command: str, eda_outputs: List[Dict], state: dict) -> Dict[str, Any]:
        """Break down user request into initial EDA subtasks"""
            
        # Context from previous EDA outputs (not code execution details)
        context = ""
        if eda_outputs:
            context_items = []
            for item in eda_outputs[-3:]:  # Last 3 EDA outputs
                context_items.append(f"Task: {item['task']}\nOutput: {item['output'][:800]}...")
            context = "\n\n".join(context_items)

        user_msg = f"""
    Previous EDA context:
    {context}

    Current user request:
    {user_command}

    Query analysis:
    {state["query_analysis"]}
    Break this down into lightweight EDA subtasks. Return valid JSON only.
    """

        try:
            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": EDA_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ],
                text={
                    "format": {"type": "json_object"},
                    "verbosity": "medium"
                },
                max_output_tokens=1000
            )

            # Update metrics in state (existing functionality - keep as is)
            state["metrics"]["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
            state["metrics"]["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
            state["metrics"]["total_tokens"] += (
                getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
            )
            state["metrics"]["successful_requests"] += 1

            content = getattr(response, "output_text", None)
            if not content:
                try:
                    content = response.output[0].content[0].text
                except Exception:
                    content = "{}"

            # Robust JSON parsing
            result = self._safe_json(content, self._fallback_plan(user_command))
            
            # Stream LLM thinking logs via progress_callback
            progress_callback = state.get("progress_callback", lambda *args, **kwargs: None)
            thinking_logs = result.get('thinking_logs', [])
            
            for i, log in enumerate(thinking_logs):
                progress_callback(f"🤖 EDA LLM #{i+1}", log, "📊")
                # Small delay to make logs visible
                await asyncio.sleep(0.2)
            
            return result
                
        except Exception as e:
            logger.error(f"Error planning EDA tasks: {e}")
            return self._fallback_plan(user_command)

    def _fallback_plan(self, user_command: str) -> Dict[str, Any]:
        """Fallback plan if JSON parsing fails"""
        return {
            "tasks": [
                {
                    "task_id": 1,
                    "description": "Execute user request",
                    "code_instruction": user_command
                }
            ]
        }

    async def analyze_completeness(self, eda_outputs: List[Dict], original_request: str, state: dict) -> Dict[str, Any]:
        """Determine if current analysis is sufficient or needs more tasks"""
        
        outputs_summary = []
        for output in eda_outputs:
            outputs_summary.append(f"Task: {output['task']}\nOutput: {output['output'][:300]}...")
        
        analysis_msg = f"""
Original request: {original_request}

Completed EDA tasks:
{chr(10).join(outputs_summary)}

Is this analysis sufficient for the original request? Return valid JSON only.
"""

        try:
            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": analysis_msg}
                ],
                text={
                    "format": {"type": "json_object"},
                    "verbosity": "medium"
                },
                max_output_tokens=500
            )

            # Update metrics in state (existing functionality - keep as is)
            state["metrics"]["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
            state["metrics"]["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
            state["metrics"]["total_tokens"] += (
                getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
            )
            state["metrics"]["successful_requests"] += 1

            content = getattr(response, "output_text", "") or ""
            json_match = re.search(r'\{.*\}', content, re.DOTALL)

            if json_match:
                return json.loads(json_match.group())
            else:
                return {"sufficient": True, "reasoning": "Analysis complete", "additional_tasks": []}
                
        except Exception as e:
            logger.error(f"Error analyzing completeness: {e}")
            return {"sufficient": True, "reasoning": "Error in analysis", "additional_tasks": []}

    async def synthesize_results(self, eda_outputs: List[Dict], image_paths: List[str], vision_report: str, state: dict) -> str:
        """Create a comprehensive summary from EDA outputs including vision analysis"""
        
        outputs_summary = []
        for output in eda_outputs:
            outputs_summary.append(f"Task: {output['task']}\nFindings: {output['output'][:400]}...")

        synthesis_input = f"""
EDA Analysis Results:
{chr(10).join(outputs_summary)}

Generated Visualizations: {len(image_paths)} chart(s)
Chart files: {', '.join(image_paths) if image_paths else 'None'}

Vision Analysis Report:
{vision_report}

Create a comprehensive EDA summary that combines both the numerical analysis results and the visual insights from the charts.
"""

        try:
            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": synthesis_input}
                ],
                max_output_tokens=1000
            )

            # Update metrics in state (existing functionality - keep as is)
            state["metrics"]["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
            state["metrics"]["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
            state["metrics"]["total_tokens"] += (
                getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
            )
            state["metrics"]["successful_requests"] += 1

            content = getattr(response, "output_text", None)
            if not content:
                try:
                    content = response.output[0].content[0].text
                except Exception:
                    content = ""
            return content
            
        except Exception as e:
            logger.error(f"Error synthesizing results: {e}")
            return f"Analysis completed with {len(eda_outputs)} tasks. Summary generation failed: {str(e)}"

    def extract_image_paths(self, code: str, output: str) -> List[str]:
        """Extract potential image file paths from code and output"""
        image_paths = []
        
        # Look for savefig calls in code
        savefig_matches = re.findall(r'plt\.savefig\([\'"]([^\'"]+)[\'"]', code)
        image_paths.extend(savefig_matches)
        
        # Look for common image file extensions in output
        image_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.pdf']
        for ext in image_extensions:
            matches = re.findall(r'([^\s]+' + re.escape(ext) + r')', output)
            image_paths.extend(matches)
        
        return image_paths

    async def execute_task(self, task: Dict, state: dict) -> Dict:
        """Execute a single EDA task using the code agent"""
        
        code_agent = CodeAgent()
        
        # Debug logging to verify EDA agent has correct paths
        print(f"🔧 [EDA AGENT] Executing task: {task['description']}")
        print(f"📥 Input dir in state: {state.get('input_dir', 'NOT SET')}")
        print(f"📤 Output dir in state: {state.get('output_dir', 'NOT SET')}")
        print(f"🆔 Job ID in state: {state.get('job_id', 'NOT SET')}")
        
        # Set the command for this specific task on the shared state
        state["command"] = task["code_instruction"]
        
        # Execute the task on the shared state
        result_state = await code_agent.ainvoke(state)
  
        # Extract image paths
        new_images = self.extract_image_paths(
            result_state.get("last_code", ""), 
            result_state.get("last_output", "")
        )
        
        # Update main state
        state["history"] = result_state["history"]
        state["last_code"] = result_state["last_code"]
        state["last_output"] = result_state["last_output"]
        state["last_error"] = result_state["last_error"]
        state["image_paths"].extend(new_images)
        
        return {
            "task": task["description"],
            "output": result_state.get("last_output", ""),
            "error": result_state.get("last_error"),
            "success": not result_state.get("last_error")
        }

    async def ainvoke(self, state: dict, config=None, **kwargs) -> dict:
        """Main EDA agent logic with iterative task execution"""
        self.state = state
        self.output_dir = self.output_dir
        original_request = state["command"]
        iteration = 0

        # Initialize required state keys
        state.setdefault("eda_outputs", [])
        state.setdefault("image_paths", [])
        state.setdefault("history", [])
        
        try:
            # Step 1: Plan initial tasks
            logger.info("Planning initial EDA tasks...")
            plan = await self.plan_initial_tasks(original_request, state["eda_outputs"], state)
            
            current_tasks = plan.get("tasks", [])
            logger.info(f"Planned {len(current_tasks)} initial tasks")
            logger.info(f"Plan: {plan}")
            
            # Iterative execution and analysis
            while iteration < self.max_iterations:
                iteration += 1
                logger.info(f"EDA Iteration {iteration}")
                
                # Step 2: Execute current tasks
                for task in current_tasks:
                    logger.info(f"Executing: {task['description']}")
                    
                    task_result = await self.execute_task(task, state)
                    state["eda_outputs"].append(task_result)
                    
                    if task_result["error"]:
                        logger.warning(f"Task failed: {task_result['error']}")
                
                # Step 3: Analyze if more tasks are needed
                logger.info("Analyzing analysis completeness...")
                completeness = await self.analyze_completeness(state["eda_outputs"], original_request, state)
                
                if completeness.get("sufficient", True) or not completeness.get("additional_tasks"):
                    logger.info(f"Analysis sufficient: {completeness.get('reasoning', 'Complete')}")
                    break
                else:
                    logger.info(f"Need more analysis: {completeness.get('reasoning', 'Continuing')}")
                    current_tasks = completeness.get("additional_tasks", [])
                    
                    # Update task IDs to avoid conflicts
                    max_id = max([len(state["eda_outputs"])], default=0)
                    for i, task in enumerate(current_tasks):
                        task["task_id"] = max_id + i + 1

            # Step 4: Vision Analysis
            logger.info("Starting vision analysis of generated images...")
            vision_report = await self.analyze_images(state)
            state["vision_analysis"] = vision_report

            # Step 5: Generate final synthesis (now includes vision analysis)
            logger.info("Generating final EDA synthesis...")
            state["eda_summary"] = await self.synthesize_results(
                state["eda_outputs"],
                state["image_paths"],
                vision_report,
                state
            )
            # print("inside eda agent",state["eda_summary"])
            state["error"] = None
            
        except Exception as e:
            logger.error(f"EDA Agent error: {e}")
            state["error"] = f"EDA Agent failed: {str(e)}"

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

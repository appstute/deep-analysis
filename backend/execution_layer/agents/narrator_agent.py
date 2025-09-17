import os
import json
import logging
import asyncio
import re
import base64
import mimetypes
from typing import List, Dict, Any
from pathlib import Path
import datetime as dt

from openai import AsyncOpenAI
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from bs4 import BeautifulSoup

from agents.executor import CodeAgent
from agents.token_manager import check_token_limit_internal, complete_job_gracefully, TokenLimitExceededException

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Updated Vision Analysis Prompt for better business context
VISION_ANALYSIS_PROMPT = """You are a senior management consultant responsible for analyzing data visualizations for executive presentations.

Your responsibilities:
1. **Chart Selection**: Determine which visualizations provide the most strategic business value
2. **Business Interpretation**: Explain what each chart reveals about the business in simple terms
3. **Executive Annotation**: Create clear annotations that highlight key insights for decision-makers
4. **Strategic Context**: Connect each visualization to the broader business question

For each visualization, provide:
- **Selection Decision**: Include/Exclude with business justification
- **Executive Summary**: 1-2 sentences explaining the key insight for busy executives
- **Business Implications**: How this insight impacts business decisions
- **Technical Details**: Brief explanation of the data represented (for appendix)
- **Recommendations**: Any additional visualizations that would strengthen the business case

Focus on creating a compelling visual narrative that drives business decisions."""

# Final Synthesis Prompt for McKinsey-style report
FINAL_SYNTHESIS_PROMPT = """You are creating a McKinsey-style executive report that transforms data analysis into strategic business insights.

IMPORTANT: You must provide detailed business-focused thinking logs throughout your analysis process so users can see your business reasoning and strategic decision-making process. Think like a business consultant, not a technical analyst.

Create a comprehensive HTML report with these characteristics:

**McKinsey-Style Elements:**
1. **Clean, minimalist design** with ample white space
2. **Blue accent color** (#003DA5) for headers and key elements
3. **Executive summary** at the beginning with key takeaways in bullet points
4. **Clear section headers** with numbering (1.0, 1.1, etc.)
5. **Highlighted key insights** in callout boxes
6. **Data tables** with minimal gridlines and clear formatting
7. **Annotated visualizations** with clear titles and insights
8. **Action-oriented recommendations** in the conclusion

**Structure:**
1. **Executive Summary** - Key findings and recommendations (1 page)
2. **Business Context** - Background and question framing
3. **Analysis Approach** - Methodology overview (brief)
4. **Key Findings** - Main insights with supporting visualizations
5. **Implications** - Business impact of findings
6. **Recommendations** - Clear, actionable next steps
7. **Appendix** - Technical details and additional data

**Technical Requirements:**
- Professional HTML with McKinsey-style CSS
- Responsive design with clean layout
- HTML tables for data summaries
- Image references using relative paths
- Indian currency formatting (₹ symbol)
- Interactive elements where appropriate
- First header should be the Question and the Date,use original_query and current_date

**Styling Instructions:**
- Do not use any external css files.
- Use only classes as a css selector for styling.
- Do not use any css element selectors like h1, p, div, span, etc for styling.
- Keep the Width of the page max 100% and initial width of the page is 100%.
- Add x-axis padding of report by 5%.
- Add proper line-height for text of report.
- Report styling should be done using classes only.
- Report styling should not make impact on other element outside report.

Make it comprehensive yet accessible to business executives.

Response format (JSON):
{
    "thinking_logs": [
        "💼 Reviewing analysis for strategic business insights...",
        "🏢 Structuring findings for executive decision-making...",
        "📈 Translating data patterns into business opportunities...",
        "🎯 Crafting actionable recommendations for stakeholders...",
        "📊 Designing executive-ready business presentation..."
    ],
    "html_report": "complete HTML code with embedded CSS"
}

Do not mention McKinsey in the report.
Make sure to include 4-6 detailed thinking_logs that show your actual reasoning process.

"""

class NarratorAgent(Runnable):
    def __init__(self, output_dir):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("MODEL_NAME", "gpt-4.1-mini")
        self.output_dir = output_dir or os.path.join('execution_layer', 'output_data')
        # Ensure narrator output directory exists
        self.narrator_dir = Path(self.output_dir) / "narrator"
        self.narrator_dir.mkdir(parents=True, exist_ok=True)

    def convert_images_to_base64(self, html_content: str) -> str:
        """
        Convert <img src> in HTML to Base64 by extracting paths from src attributes.

        Args:
            html_content (str): HTML content as string.

        Returns:
            str: Updated HTML with Base64 images.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Get current script directory for relative path resolution
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = self.output_dir
        
        logger.info(f"Converting images to Base64")
        logger.info(f"Script directory: {script_dir}")
        logger.info(f"Output directory: {output_dir}")
        
        img_tags = soup.find_all("img")
        logger.info(f"Found {len(img_tags)} img tags in HTML")
        
        for img_tag in img_tags:
            src = img_tag.get("src")
            if not src:
                continue
                
            logger.info(f"Processing image with src: {src}")
            
            try:
                # Handle relative paths
                if src.startswith("./"):
                    src = src[2:]  # Remove ./
                
                # Construct absolute path
                img_path = src
                logger.info(f"Absolute image path: {img_path}")
                
                # Get mime type
                mime_type, _ = mimetypes.guess_type(img_path)
                if mime_type is None:
                    mime_type = "image/png"
                
                # Read image and convert to Base64
                with open(img_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                
                # Replace src with Base64 data URI
                base64_src = f"data:{mime_type};base64,{encoded}"
                
                # Create a new img tag with the base64 src
                new_img_tag = soup.new_tag("img")
                new_img_tag["src"] = base64_src
                
                # Preserve all original attributes except src
                for attr_name, attr_value in img_tag.attrs.items():
                    if attr_name != "src":
                        new_img_tag[attr_name] = attr_value
                
                # Replace the old tag with the new one
                img_tag.replace_with(new_img_tag)
                
                logger.info(f"Updated src to base64 (truncated): {base64_src[:100]}...")
                logger.info(f"✅ Successfully converted {src}")
                
            except FileNotFoundError:
                logger.error(f"❌ File not found: {img_path}")
            except Exception as e:
                logger.error(f"❌ Error processing {img_path}: {str(e)}")

        # Convert back to string
        result_html = str(soup)
        logger.info(f"Final HTML length: {len(result_html)} characters")
        
        # Verify base64 data presence
        if "data:image" in result_html:
            logger.info("✅ Base64 data found in final HTML")
        else:
            logger.warning("⚠️ No base64 data found in final HTML")

        return result_html

    async def analyze_image_with_vision(self, image_path: str, context: str, state: dict) -> Dict[str, Any]:
        """Analyze image with enhanced context for graph selection and annotation"""
        try:
            if not os.path.exists(image_path):
                logger.warning(f"Image not found: {image_path}")
                return {
                    "path": image_path,
                    "selection": "exclude",
                    "reasoning": "Image file not found",
                    "executive_summary": "",
                    "business_implications": "",
                    "technical_details": "",
                    "recommendations": ""
                }
            
            logger.info(f"Analyzing image for curation: {image_path}")
            # Read and encode image
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            vision_msg = f"""
    Analyze this visualization for inclusion in executive report.

    Business Context: {context}
    Image Path: {image_path}

    Please provide:
    1. Selection decision (include/exclude) with business justification
    2. Executive summary (1-2 sentences explaining the key insight)
    3. Business implications (how this insight impacts business decisions)
    4. Technical details (brief explanation of the data represented)
    5. Recommendations (additional visualizations that would strengthen the business case)

    Return as JSON:
    {{
        "selection": "include|exclude",
        "reasoning": "business justification for inclusion/exclusion",
        "executive_summary": "1-2 sentence key insight for executives",
        "business_implications": "how this insight impacts business decisions",
        "technical_details": "brief explanation of the data represented",
        "recommendations": "additional visualizations needed"
    }}
    """
            
            # Check token limit internally before making LLM call (MULTI-USER SAFE)
            can_proceed, token_message, should_complete = check_token_limit_internal(state, estimated_tokens=800)
            
            if not can_proceed:
                if should_complete:
                    # Complete job gracefully instead of failing
                    print(f"🔥 [NARRATOR_AGENT] {token_message}")
                    return complete_job_gracefully(state)
                else:
                    # Hard failure (insufficient tokens from start)
                    state["error"] = f"🚫 PROCESS STOPPED: {token_message}"
                    print(f"🚫 [NARRATOR_AGENT] {token_message}")
                    raise TokenLimitExceededException(token_message)
            
            print(f"📊 [NARRATOR_AGENT] {token_message}")
            
            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": VISION_ANALYSIS_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": vision_msg},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/{Path(image_path).suffix[1:]};base64,{base64_image}"
                            }
                        ]
                    }
                ],
                max_output_tokens=800
            )
            
            # Update metrics in state
            state["metrics"]["prompt_tokens"] += getattr(response.usage, "input_tokens", 0) if hasattr(response, "usage") else 0
            state["metrics"]["completion_tokens"] += getattr(response.usage, "output_tokens", 0) if hasattr(response, "usage") else 0
            state["metrics"]["total_tokens"] += (
                (getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)) if hasattr(response, "usage") else 0
            )
            state["metrics"]["successful_requests"] += 1

            # Log token usage for this call
            if hasattr(response, "usage") and response.usage:
                tokens_used = getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                print(f"📊 [NARRATOR_AGENT] Used {tokens_used} tokens (Total so far: {state['metrics']['total_tokens']})")
            
            content = getattr(response, "output_text", None)
            if not content:
                try:
                    content = response.output[0].content[0].text
                except Exception:
                    content = ""
            
            # Try to parse JSON response
            try:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    result["path"] = image_path
                    return result
            except json.JSONDecodeError:
                pass
            
            # Fallback if JSON parsing fails
            return {
                "path": image_path,
                "selection": "include",
                "reasoning": "Analysis completed",
                "executive_summary": content[:150],
                "business_implications": "This visualization provides insights relevant to the business question",
                "technical_details": f"Chart from {Path(image_path).parent.name} analysis",
                "recommendations": ""
            }
            
        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {e}")
            return {
                "path": image_path,
                "selection": "exclude",
                "reasoning": f"Error analyzing image: {str(e)}",
                "executive_summary": "",
                "business_implications": "",
                "technical_details": "",
                "recommendations": ""
            }
    
    def generate_error_report(self, error_msg: str) -> str:
            """Generate a basic HTML report in case of errors"""
            return f"""
            <!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Data Analysis Report</title>
  <style>
    .mck-report {{
      font-family: Arial, Helvetica, sans-serif;
      background: #f8f9fa;
      margin: 40px;
      color: #333;
    }}
    .mck-container {{
      margin: auto;
      background: #fff;
      border-radius: 8px;
    }}
    .mck-title {{
      font-size: 24px;
      margin-bottom: 10px;
      color: #222;
    }}
    .mck-subtitle {{
      font-size: 20px;
      margin-top: 20px;
      color: #b00020;
    }}
    .mck-text {{
      font-size: 14px;
      line-height: 1.6;
    }}
    .mck-error-box {{
      border-left: 4px solid #b00020;
      background: #fff4f4;
      padding: 15px;
      margin-top: 15px;
      border-radius: 4px;
    }}
    .mck-strong {{
      color: #b00020;
      font-weight: bold;
    }}
    .mck-em {{
      font-style: italic;
    }}
  </style>
</head>
<body>
  <div class="mck-report">
    <div class="mck-container">      
      <h2 class="mck-subtitle">Generation Error</h2>
      <div class="mck-error-box">
        <p class="mck-text"><span class="mck-strong">Issue:</span> Something went wrong</p>
        <p class="mck-text">User <span class="mck-strong">{error_msg}</p>
        <p class="mck-text"><span class="mck-em">Next step:</span> For more please reach out to your administrator</p>
      </div>
    </div>
  </div>
</body>
</html>
            """
    
    def _gather_all_output_files(self) -> List[str]:
        """Collect all files under output_data directory (non-recursive)."""
        output_dir = self.output_dir
        if not os.path.exists(output_dir):
            return []
        return [str(p) for p in Path(output_dir).rglob("*") if p.is_file()]

    async def _draft_report_frame(self, state: dict, all_files: List[str]) -> Dict[str, Any]:
        """LLM call to draft narrative frame & choose up to 10 key files."""
        FRAME_PROMPT = (
            "You are a senior strategy consultant preparing a final executive report.\n"
            "Inputs: user query, hypothesis summary & findings, EDA summary, and a list of all files.\n"
            "Tasks:\n"
            "1. Write a concise narrative frame that sets the story.\n"
            "2. Select up to 10 files that best support the report.\n"
            "Return JSON: { 'frame_text': str, 'selected_files': [paths] }" )

        payload = {
            "original_query": state.get("original_query", ""),
            "hypothesis_summary": state.get("hypothesis_summary", ""),
            "hypothesis_findings": state.get("hypothesis_findings", []),
            "eda_summary": state.get("eda_summary", ""),
            "all_files": all_files,
        }

        try:
            # Check token limit internally before making LLM call (MULTI-USER SAFE)
            can_proceed, token_message, should_complete = check_token_limit_internal(state, estimated_tokens=2000)
            
            if not can_proceed:
                if should_complete:
                    # Complete job gracefully instead of failing
                    print(f"🔥 [NARRATOR_AGENT] {token_message}")
                    return complete_job_gracefully(state)
                else:
                    # Hard failure (insufficient tokens from start)
                    state["error"] = f"🚫 PROCESS STOPPED: {token_message}"
                    print(f"🚫 [NARRATOR_AGENT] {token_message}")
                    raise TokenLimitExceededException(token_message)
            
            print(f"📊 [NARRATOR_AGENT] {token_message}")
            
            response = await self.client.responses.create(
                model="gpt-4.1",
                input=[
                    {"role": "system", "content": FRAME_PROMPT},
                    {"role": "user", "content": json.dumps(payload, indent=2)}
                ],
                text={
                    "format": {"type": "json_object"},
                    "verbosity": "medium"
                },
                max_output_tokens=2000
            )

            if hasattr(response, "usage") and isinstance(state.get("metrics"), dict):
                m = state["metrics"]
                m["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
                m["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
                m["total_tokens"] += getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                m["successful_requests"] += 1

            # Log token usage for this call
            if hasattr(response, "usage") and response.usage:
                tokens_used = getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                print(f"📊 [NARRATOR_AGENT] Used {tokens_used} tokens (Total so far: {state['metrics']['total_tokens']})")

            content = getattr(response, "output_text", None)
            if not content:
                try:
                    content = response.output[0].content[0].text
                except Exception:
                    content = "{}"
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error drafting report frame: {e}")
            return {"frame_text": "", "selected_files": []}

    async def _quick_file_analysis(self, path: str, state: dict) -> Dict[str, Any]:
        """Produce a lightweight analysis summary for a single file."""
        p = Path(path)
        if not p.exists():
            return {"file": path, "error": "not found"}

        ext = p.suffix.lower()
        try:
            if ext in {".png", ".jpg", ".jpeg", ".svg"}:
                analysis = await self.analyze_image_with_vision(path, "Executive report", state)
                print("="*300)
                logger.info(f"Analysis: {path}")
                logger.info(f"Analysis: {analysis}")
                print("="*300)
                return {"file": path, "type": "image", "analysis": analysis}
            elif ext == ".csv":
                import pandas as pd
                df = pd.read_csv(p)
                return {"file": path, "type": "csv", "shape": df.shape, "columns": list(df.columns)}
            elif ext in {".txt", ".md"}:
                text = p.read_text(encoding="utf-8", errors="ignore")
                return {"file": path, "type": "text", "snippet": text[:500]}
            else:
                return {"file": path, "type": "binary", "info": "unsupported for preview"}
        except Exception as e:
            return {"file": path, "error": str(e)}

    async def _generate_final_html(self, state: dict, frame_text: str, file_analyses: List[Dict[str, Any]]) -> str:
        """Use FINAL_SYNTHESIS_PROMPT to create McKinsey-style HTML."""
        context = {
            "original_query": state.get("original_query", ""),
            "current_date": dt.datetime.now().strftime("%Y-%m-%d"),
            "frame_text": frame_text,
            "file_analyses": file_analyses,
            "hypothesis_summary": state.get("hypothesis_summary", ""),
            "hypothesis_findings": state.get("hypothesis_findings", []),
            "eda_summary": state.get("eda_summary", ""),
        }

        try:
            # Check token limit internally before making LLM call (MULTI-USER SAFE)
            can_proceed, token_message, should_complete = check_token_limit_internal(state, estimated_tokens=6000)
            
            if not can_proceed:
                if should_complete:
                    # Complete job gracefully instead of failing
                    print(f"🔥 [NARRATOR_AGENT] {token_message}")
                    return complete_job_gracefully(state)
                else:
                    # Hard failure (insufficient tokens from start)
                    state["error"] = f"🚫 PROCESS STOPPED: {token_message}"
                    print(f"🚫 [NARRATOR_AGENT] {token_message}")
                    raise TokenLimitExceededException(token_message)
            
            print(f"📊 [NARRATOR_AGENT] {token_message}")
            
            response = await self.client.responses.create(
                model="gpt-4.1",
                input=[
                    {"role": "system", "content": FINAL_SYNTHESIS_PROMPT},
                    {"role": "user", "content": json.dumps(context, indent=2)}
                ],
                text={
                    "format": {"type": "json_object"},
                    "verbosity": "medium"
                },
                max_output_tokens=6000
            )

            if hasattr(response, "usage") and isinstance(state.get("metrics"), dict):
                m = state["metrics"]
                m["prompt_tokens"] += getattr(response.usage, "input_tokens", 0)
                m["completion_tokens"] += getattr(response.usage, "output_tokens", 0)
                m["total_tokens"] += getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                m["successful_requests"] += 1

            # Log token usage for this call
            if hasattr(response, "usage") and response.usage:
                tokens_used = getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
                print(f"📊 [NARRATOR_AGENT] Used {tokens_used} tokens (Total so far: {state['metrics']['total_tokens']})")

            content = getattr(response, "output_text", None)
            if not content:
                try:
                    content = response.output[0].content[0].text
                except Exception:
                    content = "{}"
            
            try:
                result = json.loads(content)
                
                # Stream LLM thinking logs via progress_callback
                progress_callback = state.get("progress_callback", lambda *args, **kwargs: None)
                thinking_logs = result.get('thinking_logs', [])
                
                for i, log in enumerate(thinking_logs):
                    progress_callback(f"🤖 Narrator LLM #{i+1}", log, "📖")
                    # Small delay to make logs visible
                    await asyncio.sleep(0.2)
                
                html_report = result.get("html_report", "")
                return html_report.strip()
            except json.JSONDecodeError:
                # Fallback to original behavior if JSON parsing fails
                return content.strip()
        except Exception as e:
            logger.error(f"Error generating final HTML: {e}")
            return self.generate_error_report(str(e))

    async def ainvoke(self, state: dict, config=None, **kwargs) -> dict:
        """Main narrator agent logic with sequential analysis and McKinsey-style reporting"""
        
        try:
            logger.info("Starting comprehensive McKinsey-style report generation...")
            
            # Initialize metrics if not present
            if "metrics" not in state:
                state["metrics"] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "successful_requests": 0
                }
           
            # 1. Gather all files in output_data
            all_files = self._gather_all_output_files()
            logger.info(f"[Narrator] Collected {all_files} files from output_data")
            logger.info(f"[Narrator] Collected {len(all_files)} files from output_data")

            # 2. Draft report frame and select key files with LLM
            frame_dict = await self._draft_report_frame(state, all_files)
            frame_text = frame_dict.get("frame_text", "")
            selected_files = frame_dict.get("selected_files", [])
            logger.info(f"[Narrator] LLM selected {selected_files} files for deep dive")
            logger.info(f"[Narrator] LLM selected {len(selected_files)} files for deep dive")

            # 3. Analyze each selected file sequentially (lightweight)
            file_analyses = []
            for fp in selected_files:
                print("="*100)
                logger.info(f"Analyzing file: {fp}")
                print("="*100)
                analysis = await self._quick_file_analysis(fp, state)
                file_analyses.append(analysis)

            # 4. Generate final HTML report using FINAL_SYNTHESIS_PROMPT
            html_report = await self._generate_final_html(state, frame_text, file_analyses)
            
            # Clean the HTML report - handle both code block and non-code block cases
            clean_html = html_report
            if "```html" in html_report or "```" in html_report:
                # Extract HTML content from code blocks if present
                matches = re.findall(r'```(?:html)?(.*?)```', html_report, re.DOTALL)
                if matches:
                    clean_html = matches[0].strip()
                else:
                    clean_html = html_report.replace("```html", "").replace("```", "").strip()
            
            # Ensure minimal HTML structure if needed
            if not clean_html.strip().startswith("<!DOCTYPE html>"):
                clean_html = f"<!DOCTYPE html><html>{clean_html}</html>"

            # Convert images to base64
            try:
                base64_html = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.convert_images_to_base64(clean_html)
                )
            except Exception as e:
                logger.error(f"Error converting images to base64: {e}")
                base64_html = clean_html  # Fallback to clean HTML if base64 conversion fails

            logger.info("Generated report details:")
            logger.info(f"Original length: {len(html_report)}")
            logger.info(f"Cleaned length: {len(clean_html)}")
            logger.info(f"Base64 length: {len(base64_html)}")
            logger.info(f"Contains base64 images: {'data:image' in base64_html}")

            # 5. Save outputs to state and disk for downstream use
            state["final_html_report"] = base64_html
            state["narrator_frame_text"] = frame_text
            state["narrator_file_analyses"] = file_analyses
 
        except Exception as e:
            logger.error(f"Narrator Agent error: {e}")
            state["error"] = f"Narrator Agent failed: {str(e)}"
            
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

from jupyter_client.manager import KernelManager
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool

class CodeExecutionInput(BaseModel):
    code: str = Field(..., description="Python code to execute")
    description: Optional[str] = Field(None, description="Description of the code")

class JupyterExecutionTool:
    def __init__(self):
        self.km = KernelManager()
        self.km.start_kernel()
        self.kc = self.km.client()
        self.kc.start_channels()
        
        # Initialize kernel with common imports
        self._setup_kernel()

    def _setup_kernel(self):
        setup_code = """
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        import seaborn as sns
        from IPython.display import display
        %matplotlib inline
        plt.style.use('ggplot')
        """
        self.execute_code(setup_code)

    def execute_code(self, code: str) -> Dict[str, Any]:
        outputs = []
        error = None
        
        try:
            msg_id = self.kc.execute(code)
            while True:
                msg = self.kc.get_iopub_msg(timeout=10)
                if msg['parent_header'].get('msg_id') != msg_id:
                    continue
                    
                msg_type = msg['header']['msg_type']
                content = msg['content']
                
                if msg_type == 'execute_result' or msg_type == 'display_data':
                    if 'text/plain' in content['data']:
                        outputs.append(content['data']['text/plain'])
                elif msg_type == 'stream':
                    outputs.append(content['text'])
                elif msg_type == 'error':
                    error = f"Error: {content['ename']}: {content['evalue']}"
                    outputs.append(error)
                if msg_type == 'status' and content['execution_state'] == 'idle':
                    break
                    
        except Exception as e:
            error = f"Execution error: {str(e)}"
            outputs.append(error)
            
        return {
            "output": "\n".join(outputs),
            "error": error,
            "success": error is None
        }

    def cleanup(self):
        self.kc.stop_channels()
        self.km.shutdown_kernel()

    def get_tool(self) -> StructuredTool:
        def execute_wrapper(code: str, description: Optional[str] = None) -> Dict[str, Any]:
            return self.execute_code(code)
            
        return StructuredTool(
            name="code_executor",
            description="Executes Python code in a Jupyter kernel and returns the output",
            func=execute_wrapper,
            args_schema=CodeExecutionInput
        )


# if __name__ == "__main__":
#     # Instantiate the tool
#     jupyter_tool = JupyterExecutionTool()
#     code_executor = jupyter_tool.get_tool()

#     # Prepare test input according to CodeExecutionInput schema
#     test_code = "print('hello')"
#     tool_input = {"code": test_code}

#     # Execute and capture the result
#     result = code_executor.run(tool_input)

#     # Display results
#     print("Test Results:")
#     print(f"Output: {result['output']}")
#     print(f"Error: {result['error']}")
#     print(f"Success: {result['success']}")

#     # Shutdown kernel
#     jupyter_tool.cleanup()

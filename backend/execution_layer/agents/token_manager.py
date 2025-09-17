from typing import Dict, Any


def check_token_limit_internal(state: Dict[str, Any], estimated_tokens: int = 0) -> tuple[bool, str, bool]:
    """
    Check if user has enough tokens remaining using internal tracking
    
    Returns:
        Tuple of (can_proceed, message, should_complete_job)
        - can_proceed: True if operation can proceed
        - message: Status message
        - should_complete_job: True if job should complete gracefully instead of failing
    """
    try:
        user_email = state.get("user_email", "")
        user_token_info = state.get("user_token_info", {})
        
        if not user_token_info or not user_email:
            return True, "No token info available - allowing operation", False
        
        # Get token limits
        initial_used = user_token_info.get('used_token', 0)
        issued_tokens = user_token_info.get('issued_token', 0)
        current_used_in_job = state["metrics"]["total_tokens"]  # Tokens used so far in this job
        total_used_so_far = initial_used + current_used_in_job
        remaining_tokens = issued_tokens - total_used_so_far
        
        # CRITICAL: Ensure used tokens never exceed issued tokens
        if total_used_so_far >= issued_tokens:
            # Token limit already reached/exceeded - complete job gracefully
            state["tokens_exhausted"] = True
            state["token_exhaustion_message"] = f"Token limit reached. Used: {total_used_so_far:,}/{issued_tokens:,} tokens."
            completion_msg = f"🔥 TOKENS EXHAUSTED! Used {total_used_so_far:,}/{issued_tokens:,} tokens. Completing analysis with current results."
            print(f"🔥 [TOKEN LIMIT] {completion_msg}")
            return False, completion_msg, True  # Don't proceed, but complete job gracefully
        
        # Check if estimated tokens would exceed limit
        if estimated_tokens > 0 and (total_used_so_far + estimated_tokens) > issued_tokens:
            # Would exceed limit - complete job gracefully
            state["tokens_exhausted"] = True  
            state["token_exhaustion_message"] = f"Token limit would be exceeded. Need {estimated_tokens:,}, have {remaining_tokens:,} remaining."
            completion_msg = f"🔥 TOKENS NEARLY EXHAUSTED! Need {estimated_tokens:,}, have {remaining_tokens:,} remaining. Completing analysis with current results."
            print(f"🔥 [TOKEN LIMIT] {completion_msg}")
            return False, completion_msg, True  # Don't proceed, but complete job gracefully
        
        # Sufficient tokens available
        return True, f"✅ Sufficient tokens: {remaining_tokens:,} remaining for user {user_email} (used: {total_used_so_far:,}/{issued_tokens:,})", False
        
    except Exception as e:
        print(f"❌ Error in internal token check: {str(e)}")
        return True, f"Token check error - allowing operation: {str(e)}", False


def complete_job_gracefully(state: Dict[str, Any]) -> Dict[str, Any]:
    """Complete job gracefully when tokens are exhausted"""
    user_email = state.get("user_email", "")
    token_message = state.get("token_exhaustion_message", "Token limit reached")
    
    print(f"🔥 [GRACEFUL COMPLETION] Completing job for user {user_email}: {token_message}")
    
    # Set completion flags
    state["analysis_completed_early"] = True
    state["completion_reason"] = "token_limit_reached"
    state["final_message"] = f"Analysis completed with available tokens. {token_message}"
    
    # Ensure we have some basic structure for the report
    if not state.get("final_html_report"):
        partial_report = f"""
        <!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    .mck-report {{
      font-family: Arial, Helvetica, sans-serif;
      margin: 40px;
      color: #333;
    }}
    .mck-container {{
      max-width: 800px;
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
        <p class="mck-text"><span class="mck-strong">Issue:</span> Token limit exhausted.</p>
        <p class="mck-text">User <span class="mck-strong">samarth.mali@zingworks.in</span> has no tokens remaining.</p>
        <p class="mck-text"><span class="mck-em">Next step:</span> Contact your admin to allocate additional tokens before retrying.</p>
      </div>
    </div>
  </div>
</body>
</html>

        """
        state["final_html_report"] = partial_report
    
    return state


class TokenLimitExceededException(Exception):
    """Exception raised when user's token limit is exceeded"""
    
    pass

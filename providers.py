import time

def call_openai(api_key, model, system, user_content, max_tokens=600):
    import openai
    client = openai.OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            timeout=60.0
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"OpenAI API Hatasi: {e}")

def call_anthropic(api_key, model, system, user_content, max_tokens=600):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            timeout=60.0
        )
        for block in resp.content:
            if block.type == "text":
                return block.text
        return ""
    except Exception as e:
        raise RuntimeError(f"Anthropic API Hatasi: {e}")

def call_gemini(api_key, model, system, user_content, max_tokens=600):
    from google import genai
    from google.genai import types
    
    client = genai.Client(api_key=api_key)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                )
            )
            return resp.text
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "quota" in err_msg:
                if attempt < max_retries - 1:
                    time.sleep(60.0)
                    continue
            raise RuntimeError(f"Gemini API Hatasi: {e}")

PROVIDER_CALLERS = {
    "openai": call_openai,
    "anthropic": call_anthropic,
    "gemini": call_gemini,
}

PROVIDER_LABELS = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "gemini": "Google (Gemini)",
}

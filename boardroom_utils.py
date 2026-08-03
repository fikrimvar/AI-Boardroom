import litellm

def track_cost(response):
    try:
        if not response:
            return 0.0
        # LiteLLM'in iç loglarını tamamen sustur
        litellm.set_verbose = False 
        cost = litellm.completion_cost(completion_response=response)
        usage = response.get('usage', {})
        print(f"--- [OK] Token: {usage.get('total_tokens', 0)} | Maliyet: ${cost or 0:.5f} ---")
        return cost or 0.0
    except Exception as e:
        print(f"[COST HATA] {str(e)}")
        return 0.0
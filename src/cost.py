def compute_cost(input_tokens, output_tokens, cache_creation, cache_read, model):
    """Compute estimated API list-price cost in USD."""
    if 'opus' in model:
        return (input_tokens * 15 / 1e6 + cache_creation * 18.75 / 1e6 +
                cache_read * 1.50 / 1e6 + output_tokens * 75 / 1e6)
    return (input_tokens * 3 / 1e6 + cache_creation * 3.75 / 1e6 +
            cache_read * 0.30 / 1e6 + output_tokens * 15 / 1e6)

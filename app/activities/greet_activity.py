from temporalio import activity


@activity.defn
async def greet(name: str) -> str:
    """Simple activity that returns a greeting."""
    return f"Hello, {name}!"

from agentos.memory import default_memory
from agentos.tools import tool

# Unlike memory/kv (scoped per API key), a connected Instagram/LinkedIn
# account is one real external account tied to this deployment, not to
# any individual caller - the same "shared operator-level credential"
# model already used for SMTP/IMAP. Every caller's agent posts through
# the same connected account.
_SHARED_SCOPE = "default"


@tool(
    "Post a photo to Instagram (the connected Business/Creator account). "
    "Requires Instagram to already be connected via GET /auth/instagram/login "
    "on this deployment - if it isn't, this returns instructions instead "
    "of posting, which you should relay to the user rather than retrying.",
    {
        "type": "object",
        "properties": {
            "image_url": {
                "type": "string",
                "description": "a publicly reachable URL of the image to post "
                               "(Instagram fetches it directly, so it can't be "
                               "a local file)",
            },
            "caption": {"type": "string"},
        },
        "required": ["image_url", "caption"],
    },
    requires_approval=True,
)
def post_to_instagram(image_url, caption):
    from agentos import social_instagram

    token = default_memory.get_social_token(_SHARED_SCOPE, "instagram")
    if not token:
        return ("Instagram is not connected for this account. Visit "
                "/auth/instagram/login on this deployment to connect it, "
                "then try again.")

    try:
        post_id = social_instagram.publish_photo(
            token["access_token"], token["account_id"], image_url, caption)
        return f"Posted to Instagram (id: {post_id})."
    except Exception as e:
        return f"Instagram post failed: {e}"


@tool(
    "Post text to LinkedIn (the connected personal profile). Requires "
    "LinkedIn to already be connected via GET /auth/linkedin/login on "
    "this deployment - if it isn't, this returns instructions instead of "
    "posting, which you should relay to the user rather than retrying.",
    {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    requires_approval=True,
)
def post_to_linkedin(text):
    from agentos import social_linkedin

    token = default_memory.get_social_token(_SHARED_SCOPE, "linkedin")
    if not token:
        return ("LinkedIn is not connected for this account. Visit "
                "/auth/linkedin/login on this deployment to connect it, "
                "then try again.")

    try:
        post_urn = social_linkedin.publish_text_post(
            token["access_token"], token["account_id"], text)
        return f"Posted to LinkedIn (id: {post_urn})."
    except Exception as e:
        return f"LinkedIn post failed: {e}"

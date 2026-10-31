import os
import re
from typing import Dict, Any, Optional, Union
import httpx
from openai import OpenAI
from app.config import settings
from app.database import ProspectModel, EmailThreadModel, AutomationSettingsModel

class AIFollowUpService:
    @staticmethod
    def get_anthropic_api_key() -> Optional[str]:
        return (
            settings.ANTHROPIC_API_KEY or 
            settings.CLAUDE_API_KEY or 
            os.environ.get("ANTHROPIC_API_KEY") or 
            os.environ.get("CLAUDE_API_KEY")
        )

    @staticmethod
    def get_openai_client() -> Optional[OpenAI]:
        api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
        if api_key and api_key.startswith("sk-") and len(api_key) > 20:
            return OpenAI(api_key=api_key)
        return None

    @classmethod
    def generate_follow_up(
        cls, 
        target: Union[ProspectModel, EmailThreadModel, Any], 
        settings_override: Optional[AutomationSettingsModel] = None,
        custom_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a personalized, concise follow-up email adhering to original context,
        tone, and business value proposition.
        Supports Anthropic Claude API and OpenAI API seamlessly.
        """
        # Extract fields flexibly
        if hasattr(target, 'prospect') and getattr(target, 'prospect', None) is not None:
            prospect_name = target.prospect.name or "there"
            company_name = target.prospect.company or "your company"
            orig_subject = getattr(target, 'original_subject', None) or "Our conversation"
            orig_body = getattr(target, 'original_body', None) or ""
        elif hasattr(target, 'email'):
            prospect_name = getattr(target, 'name', None) or "there"
            company_name = getattr(target, 'company', None) or "your company"
            orig_subject = getattr(target, 'original_subject', None) or "Our previous discussion"
            orig_body = getattr(target, 'original_body', None) or ""
        else:
            prospect_name = "there"
            company_name = "your company"
            orig_subject = getattr(target, 'original_subject', None) or "Our conversation"
            orig_body = getattr(target, 'original_body', None) or ""

        account_settings = settings_override
        configured_model = account_settings.ai_model if account_settings and account_settings.ai_model else settings.OPENAI_DEFAULT_MODEL
        instructions = custom_instructions or (account_settings.ai_instructions if account_settings else "")
        signature = account_settings.email_signature if account_settings and account_settings.email_signature else "Best regards,"
        max_words = 120

        followup_subject = orig_subject
        if not followup_subject.lower().startswith("re:"):
            followup_subject = f"Re: {orig_subject}"

        system_prompt = (
            "You are an expert executive sales assistant and cold email copywriter.\n"
            "Your objective is to write a short, highly personalized, polite follow-up email.\n\n"
            "STRICT RULES:\n"
            "1. Read the original outreach email carefully to understand the exact proposition and offer.\n"
            "2. Do NOT invent false claims or facts about the prospect or their company.\n"
            "3. Do NOT repeat the initial email word-for-word.\n"
            "4. Keep the email concise (between 40 and 85 words).\n"
            "5. Never sound desperate, needy, or aggressive (avoid: 'Since I haven't heard from you', 'Bumping this to top of inbox').\n"
            "6. Maintain a natural, confident, and professional tone.\n"
            f"7. End with the specified signature: '{signature}'\n"
            f"8. Maximum length: {max_words} words."
        )

        user_prompt = (
            f"Prospect Name: {prospect_name}\n"
            f"Company: {company_name}\n"
            f"Original Subject: {orig_subject}\n"
            f"Original Email Body:\n---\n{orig_body}\n---\n\n"
            f"User Custom Instructions: {instructions}\n\n"
            "Write the follow-up email text now:"
        )

        claude_key = cls.get_anthropic_api_key()
        openai_client = cls.get_openai_client()

        # Decide which provider to use:
        # Prefer Claude if model contains 'claude' or if Claude key exists and no OpenAI key
        use_claude = bool(claude_key and ("claude" in configured_model.lower() or not openai_client))

        # 1. GENERATE VIA ANTHROPIC CLAUDE API
        if use_claude and claude_key:
            actual_claude_model = configured_model if "claude" in configured_model.lower() else "claude-3-5-haiku-20241022"
            try:
                headers = {
                    "x-api-key": claude_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": actual_claude_model,
                    "max_tokens": 250,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ]
                }
                resp = httpx.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=25.0)
                if resp.status_code == 200:
                    data = resp.json()
                    content_blocks = data.get("content", [])
                    generated_text = "".join(b.get("text", "") for b in content_blocks).strip()
                    if generated_text:
                        return {
                            "subject": followup_subject,
                            "body": generated_text,
                            "model": actual_claude_model,
                            "provider": "Anthropic Claude",
                            "is_fallback": False
                        }
                error_detail = resp.text
                return cls._generate_algorithmic_fallback(
                    prospect_name, company_name, orig_subject, orig_body, signature, f"Claude API notice ({resp.status_code}): {error_detail[:120]}"
                )
            except Exception as e:
                return cls._generate_algorithmic_fallback(
                    prospect_name, company_name, orig_subject, orig_body, signature, f"Claude API error: {str(e)}"
                )

        # 2. GENERATE VIA OPENAI API
        if openai_client:
            actual_openai_model = configured_model if not "claude" in configured_model.lower() else "gpt-4o-mini"
            try:
                response = openai_client.chat.completions.create(
                    model=actual_openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=250
                )
                generated_body = response.choices[0].message.content.strip()
                return {
                    "subject": followup_subject,
                    "body": generated_body,
                    "model": actual_openai_model,
                    "provider": "OpenAI",
                    "is_fallback": False
                }
            except Exception as e:
                return cls._generate_algorithmic_fallback(
                    prospect_name, company_name, orig_subject, orig_body, signature, str(e)
                )

        # 3. ALGORITHMIC INTELLIGENT FALLBACK (when no API key is set)
        return cls._generate_algorithmic_fallback(
            prospect_name, company_name, orig_subject, orig_body, signature, 
            "No AI API key set. Provide ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY."
        )

    @classmethod
    def _generate_algorithmic_fallback(
        cls, 
        name: str,
        company: str,
        orig_subject: str, 
        orig_body: str, 
        signature: str,
        note: str
    ) -> Dict[str, Any]:
        followup_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
        company_mention = f" for {company}" if company and company != "your company" else ""

        body = (
            f"Hi {name},\n\n"
            f"Just following up on my previous email regarding {orig_subject.replace('Re:', '').strip()}.\n\n"
            f"I wanted to see if exploring this{company_mention} might be relevant for your team this quarter. "
            "Would you be open to a brief 10-minute introductory call next week?\n\n"
            f"{signature}"
        )

        return {
            "subject": followup_subject,
            "body": body,
            "model": "rule-based-fallback",
            "is_fallback": True,
            "warning": note
        }

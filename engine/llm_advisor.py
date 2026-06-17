"""
LLM Advisor — Boost des signaux via Claude (Anthropic) ou GPT-4o-mini (OpenAI)
Fournit une analyse contextuelle optionnelle pour enrichir le signal composite
Appelé seulement si le score est borderline (40-60) ou si demandé explicitement
"""
from __future__ import annotations
import os
import json
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger('dte.llm_advisor')

# Seuils pour déclencher le LLM
BORDERLINE_LOW  = 40.0
BORDERLINE_HIGH = 65.0


class LLMAdvisor:
    """
    Analyse le signal composite avec un LLM pour affiner la décision.
    Utilise Anthropic Claude en priorité, OpenAI GPT-4o-mini en fallback.
    """

    def __init__(
        self,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        model_anthropic: str = 'claude-haiku-4-5-20251001',
        model_openai: str = 'gpt-4o-mini',
        enabled: bool = True,
    ):
        self.anthropic_key = anthropic_key or os.getenv('ANTHROPIC_API_KEY', '')
        self.openai_key = openai_key or os.getenv('OPENAI_API_KEY', '')
        self.model_anthropic = model_anthropic
        self.model_openai = model_openai
        self.enabled = enabled
        self._client_anthropic = None
        self._client_openai = None
        self._init_clients()

    def _init_clients(self):
        if self.anthropic_key:
            try:
                import anthropic
                self._client_anthropic = anthropic.Anthropic(api_key=self.anthropic_key)
                logger.info('LLM Anthropic client initialisé')
            except ImportError:
                logger.warning('Package anthropic non installé (pip install anthropic)')
        if self.openai_key and not self._client_anthropic:
            try:
                from openai import OpenAI
                self._client_openai = OpenAI(api_key=self.openai_key)
                logger.info('LLM OpenAI client initialisé (fallback)')
            except ImportError:
                logger.warning('Package openai non installé')

    def _build_prompt(self, signal_dict: dict, account_balance: float) -> str:
        return f"""Tu es un expert en trading algorithmique sur les indices synthétiques Deriv (RNG certifiés).
Tu dois analyser le signal composite et donner une recommandation BRÈVE et PRÉCISE.

SIGNAL ACTUEL ({datetime.now().strftime('%H:%M:%S')}):
- Actif: {signal_dict.get('symbol')}
- Action brute: {signal_dict.get('action')}
- Score composite: {signal_dict.get('score')}/100
- Direction: {'LONG' if signal_dict.get('direction', 0) > 0 else 'SHORT' if signal_dict.get('direction', 0) < 0 else 'NEUTRE'}
- Confiance: {signal_dict.get('confidence')}
- Alignement modes: {signal_dict.get('alignment')}/3
- Score modèle A (Streaks): {signal_dict.get('scores', {}).get('A', 0)}
- Score modèle B (Volatilité): {signal_dict.get('scores', {}).get('B', 0)}
- Score modèle C (Événement/Spike): {signal_dict.get('scores', {}).get('C', 0)}
- Score modèle D (Monte Carlo): {signal_dict.get('scores', {}).get('D', 0)}
- Alerte spike: {signal_dict.get('spike_alert')} ({signal_dict.get('spike_alert_level', '')})
- Réduire mise: {signal_dict.get('reduce_size')}
- Solde compte: {account_balance:.2f}

Réponds UNIQUEMENT en JSON avec ce format exact:
{{"confirmed": true/false, "adjusted_score": <0-100>, "reason": "<20 mots max>", "risk": "LOW/MEDIUM/HIGH"}}

RÈGLES: Les synthétiques sont des RNG. Ne confirme PAS si score < 40.
Pour Crash/Boom, la directionnalité forte (90%+) est exploitable."""

    def _call_anthropic(self, prompt: str) -> Optional[dict]:
        try:
            msg = self._client_anthropic.messages.create(
                model=self.model_anthropic,
                max_tokens=150,
                messages=[{'role': 'user', 'content': prompt}],
            )
            text = msg.content[0].text.strip()
            # Extraire le JSON de la réponse
            if '{' in text and '}' in text:
                text = text[text.index('{'):text.rindex('}') + 1]
            return json.loads(text)
        except Exception as e:
            logger.warning(f'Anthropic call failed: {e}')
            return None

    def _call_openai(self, prompt: str) -> Optional[dict]:
        try:
            resp = self._client_openai.chat.completions.create(
                model=self.model_openai,
                max_tokens=150,
                response_format={'type': 'json_object'},
                messages=[{'role': 'user', 'content': prompt}],
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.warning(f'OpenAI call failed: {e}')
            return None

    def advise(
        self,
        signal_dict: dict,
        account_balance: float = 0.0,
        force: bool = False,
    ) -> dict:
        """
        Retourne une analyse LLM enrichie du signal.
        N'appelle le LLM que si le signal est borderline ou si force=True.
        """
        score = signal_dict.get('score', 0)
        is_borderline = BORDERLINE_LOW <= score <= BORDERLINE_HIGH
        should_call = self.enabled and (is_borderline or force)

        if not should_call or (not self._client_anthropic and not self._client_openai):
            return {
                'llm_used': False,
                'confirmed': signal_dict.get('action') != 'WAIT',
                'adjusted_score': score,
                'reason': 'LLM non appelé (hors zone borderline ou désactivé)',
                'risk': 'MEDIUM',
            }

        prompt = self._build_prompt(signal_dict, account_balance)

        # Anthropic en priorité
        result = None
        provider = 'none'
        if self._client_anthropic:
            result = self._call_anthropic(prompt)
            provider = 'anthropic'
        if result is None and self._client_openai:
            result = self._call_openai(prompt)
            provider = 'openai'

        if result is None:
            return {
                'llm_used': False,
                'confirmed': signal_dict.get('action') != 'WAIT',
                'adjusted_score': score,
                'reason': 'LLM indisponible — signal brut conservé',
                'risk': 'MEDIUM',
            }

        logger.info(f'LLM ({provider}) → {result}')
        return {
            'llm_used': True,
            'provider': provider,
            'confirmed': result.get('confirmed', True),
            'adjusted_score': float(result.get('adjusted_score', score)),
            'reason': result.get('reason', ''),
            'risk': result.get('risk', 'MEDIUM'),
        }

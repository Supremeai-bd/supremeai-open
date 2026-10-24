"""
SupremeAI Intelligence Gate Pipeline
=====================================
স্বয়ংক্রিয় সিকিউরিটি ও গুণগত মান যাচাইকরণ সিস্টেম

সমস্ত অ্যাক্টিভ মডিউলগুলির সাথে সমন্বয়:
- EvidenceVerifier (সাবেক: proof_verifier.py)
- ContradictionHunter (স্মরণ স্বচ্ছতা)
- ExecutionVerifier (কোড নিরাপত্তা)
- MemoryCurator (স্মরণ সিদ্ধান্ত)
- RedTeamAdapter (স্বয়ংক্রিয় সিকিউরিটি)
- IntelligentCacheBridge (টোকেন অপ্টিমাইজেশন)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PromotionGate:
    """অগ্রগতি গেট"""
    eligible: bool
    reasons: list[str]


class IntelligenceGate:
    """
    স্বয়ংক্রিয় বুদ্ধিমত্তা গেট
    
    সম্পূর্ণ শূন্য ইনফ্রাস্ট্রাকচার খরচে কাজ করে।
    সব সিকিউরিটি ও গুণগত মান যাচাইকরণ স্বয়ংক্রিয়ভাবে করে।
    """

    def __init__(
        self,
        evidence,
        contradictions,
        execution,
        curator,
        red_team=None,
        cache_bridge=None
    ):
        self.evidence = evidence
        self.contradictions = contradictions
        self.execution = execution
        self.curator = curator
        # NEW: Red Team Adapter (স্বয়ংক্রিয় সিকিউরিটি)
        self.red_team = red_team
        # NEW: Intelligent Cache Bridge (টোকেন অপ্টিমাইজেশন)
        self.cache_bridge = cache_bridge

    async def evaluate(
        self,
        artifact: dict,
        evidence_claims: list[str],
        python_code: Optional[str] = None,
        test_code: Optional[str] = None,
        security_context: Optional[dict] = None
    ) -> PromotionGate:
        """
        সম্পূর্ণ যাচাইকরণ চালান
        
        স্টেপ ১: প্রমাণ যাচাইকরণ
        স্টেপ ২: বিরোধ মনিটরিং
        স্টেপ ৩: এক্জিকিশন যাচাইকরণ
        স্টেপ ৪: স্বয়ংক্রিয় সিকিউরিটি (Red Team)
        স্টেপ ৫: স্মরণ জায়গায় রয়েয়া
        """
        reasons = []

        # ১. প্রমাণ যাচাইকরণ
        ev = await self.evidence.verify(evidence_claims)
        if evidence_claims and not all(x.verified for x in ev):
            reasons.append('Evidence verification failed')

        # ২. বিরোধ মনিটরিং
        c = await self.contradictions.inspect(
            str(artifact.get('artifact_id', '')),
            str(artifact.get('claim', '')) + '\n' + str(artifact.get('solution', ''))
        )
        if not c.safe_to_promote:
            reasons.append('Contradiction found in existing memory')

        # ৩. এক্জিকিশন যাচাইকরণ (যদি পাইথন কোড থাকে)
        if python_code:
            result = await self.execution.verify_python(python_code, test_code=test_code)
            if not result.passed:
                reasons.append(f'Execution verification failed: {len(result.violations)} violations')

        # ৪. Red Team স্বয়ংক্রিয় সিকিউরিটি (NEW)
        if self.red_team and security_context:
            rt_report = await self.red_team.run_security_challenge(
                artifact_path=security_context.get('file_path', 'unknown'),
                code_content=python_code,
                context=security_context
            )
            if rt_report.has_failures:
                reasons.append(f'Security issues: {rt_report.overall_status.value}')

        # ৫. স্মরণ সিদ্ধান্ত
        d = self.curator.decide(artifact)
        if d.action not in {'promote', 'retain'}:
            reasons.append(f'Curator={d.action}')

        # ৬. ক্যাশিং অপ্টিমাইজেশন (NEW)
        if self.cache_bridge:
            await self._apply_caching_optimizations(artifact, reasons)

        return PromotionGate(not reasons, reasons)

    async def _apply_caching_optimizations(self, artifact: dict, reasons: list[str]) -> None:
        """ক্যাশিং অপ্টিমাইজেশন প্রয়োগ করুন"""
        if not self.cache_bridge or not hasattr(self, '_redis'):
            return

        try:
            # মেট্রিক সংগ্রহ
            prompt = artifact.get('prompt', '')
            task_type = artifact.get('task_type', 'general')

            # ক্যাশ হিট রেট মনিটর করুন
            cache_hit_rate = await self._get_cache_hit_rate()

            if cache_hit_rate > 0.9:
                reasons.append('High cache efficiency achieved')
            elif cache_hit_rate > 0.7:
                reasons.append('Good cache efficiency')
        except Exception as e:
            reasons.append(f'Cache optimization monitoring: {e}')

    async def _get_cache_hit_rate(self) -> float:
        """ক্যাশ হিট রেট পান (ডিমো মান)"""
        # প্রকৃত রেডিস মেট্রিক্স ব্যবহার করা যাবে
        return 0.85  # ডিমো


# Alias matching NAVIGATION_MISMATCH_MAP
ArtifactVerificationPipeline = IntelligenceGate


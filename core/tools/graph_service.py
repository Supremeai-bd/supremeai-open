try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    AsyncGraphDatabase = None

from core.config import settings
from core.logging_config import logger

# বাংলা মন্তব্য: স্কিল ইন্টিগ্রেশন এবং নলেজ গ্রাফ ম্যাপিং করার সার্ভিস লেয়ার।


class GraphService:
    def __init__(self):
        # বাংলা মন্তব্য: Neo4j Aura (ফ্রি টিয়ার) এর ক্রেডেনশিয়াল
        # BE-14 (issue #546): settings আর localhost/'neo4j' default দেয় না —
        # unconfigured হলে খালি মান আসে, এবং নিচের fail-closed চেক dry-run-এ যায়।
        self.uri = getattr(settings, "neo4j_uri", "") or ""
        self.user = getattr(settings, "neo4j_user", "") or ""
        self.password = getattr(settings, "neo4j_password", None)

        # বাংলা মন্তব্য: যদি পাসওয়ার্ড না থাকে, অথবা টেস্ট এনভায়রনমেন্টে মক সিক্রেট থাকে (যেমন: 'mock_NEO4J_URI'), তবে ড্রাই-রান মোড চালু হবে।
        # BE-14 (issue #546): fail-closed — NEO4J_URI/NEO4J_USER ছাড়া আর
        # localhost/'neo4j' অনুমান করা হয় না; configure না থাকলে dry-run।
        self.dry_run = (
            not self.password
            or not self.uri
            or not self.user
            or self.uri.startswith("mock_")
            or (isinstance(self.password, str) and self.password.startswith("mock_"))
        )

        if self.dry_run:
            logger.warning(
                "NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD missing or mock credentials detected. "
                "GraphService will run in dry-run/mock mode (no implicit localhost fallback, BE-14)."
            )
            self.driver = None
        else:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
            logger.info("Initialized Neo4j GraphService")

    async def close(self):
        if self.driver:
            await self.driver.close()

    async def sync_skills_to_graph(self, skills: list[dict]):
        """বাংলা মন্তব্য: স্কিলগুলোকে নোড (Node) হিসেবে গ্রাফ ডাটাবেসে সিঙ্ক করবে।"""
        if self.dry_run:
            logger.info(f"Dry-run: Would sync {len(skills)} skills to graph.")
            return True

        async with self.driver.session() as session:
            for skill in skills:
                await session.run(
                    "MERGE (s:Skill {id: $id}) SET s.name = $name, s.category = $category, s.success_rate = $success_rate",
                    id=skill["id"],
                    name=skill["name"],
                    category=skill["category"],
                    success_rate=skill.get("success_rate", 0.0),
                )
        return True

    async def create_relationship(
        self, source_id: str, target_id: str, rel_type: str, strength: float = 1.0
    ):
        """বাংলা মন্তব্য: দুটি স্কিলের মধ্যে রিলেশনシップ (Edge) তৈরি করবে।"""
        if self.dry_run:
            logger.info(f"Dry-run: Would create {rel_type} between {source_id} and {target_id}.")
            return True

        async with self.driver.session() as session:
            query = f"MATCH (s1:Skill {{id: $source}}), (s2:Skill {{id: $target}}) MERGE (s1)-[r:{rel_type}]->(s2) SET r.strength = $strength"
            await session.run(query, source=source_id, target=target_id, strength=strength)
        return True

    async def get_skill_path(self, start_name: str, end_name: str) -> list[str]:
        """বাংলা মন্তব্য: একটি স্কিল থেকে অন্য স্কিলে যাওয়ার লার্নিং পাথ বের করবে।"""
        if self.dry_run:
            return ["Dry-run Path Node 1", "Dry-run Path Node 2"]

        async with self.driver.session() as session:
            result = await session.run(
                "MATCH path = shortestPath((start:Skill {name: $start})-[:DEPENDS_ON|PREREQUISITE*1..10]-(end:Skill {name: $end})) "
                "RETURN [n in nodes(path) | n.name] AS path",
                start=start_name,
                end=end_name,
            )
            records = await result.data()
            return records[0]["path"] if records else []

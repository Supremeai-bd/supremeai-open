"""This module establishes the fundamental `BaseSkill` abstract base class, serving as the core contract for all executable skills within the SupremeAI ecosystem. It mandates that every concrete skill implementation must provide an asynchronous `execute` method, thereby standardizing the interface for agents to interact with and leverage diverse capabilities across the platform. This foundational structure is crucial for maintaining consistency and interoperability among the various agentic tools.

Key Components:
- `BaseSkill`: An abstract base class that defines the essential interface and contract for all skills, ensuring they adhere to a common structure and implement core execution logic.
- `BaseSkill.execute()`: An abstract asynchronous method that concrete skill implementations must override to encapsulate their specific operational logic and return a result.
- `BaseSkill.name`: A property that provides the string name of the skill, typically derived from its class name, for identification purposes.

Dependencies:
- `abc`: Utilized for defining abstract base classes (`ABC`) and abstract methods (`abstractmethod`), enforcing the skill contract.
- `typing`: Used for type hinting, specifically `Any`, to indicate flexible input and output types for skill execution.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """
    বাংলা মন্তব্য: সকল স্কিলের জন্য অ্যাবস্ট্র্যাক্ট বেস ক্লাস (The Contract)।
    প্রতিটি স্কিলকে অবশ্যই একটি async `execute` মেথড ইমপ্লিমেন্ট করতে হবে।
    """

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        বাংলা মন্তব্য: এই মেথডটি স্কিলের মূল লজিক ধারণ করবে।
        """
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__

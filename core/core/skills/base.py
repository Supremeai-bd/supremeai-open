class BaseSkill:
    """Base class for all skills."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def run(self, *args, **kwargs):
        raise NotImplementedError

from typing import Any, Callable, Dict, List, Optional


class Provider:
    """
    Base provider abstraction.

    - `name`: human-readable provider name shown in menus.
    - `operations`: mapping between operation labels and zero-argument callables
      that execute the operation.
    """

    # Explicit, Pylance-friendly attribute type annotations.
    name: str
    operations: Dict[str, Callable[[], Any]]  # Each operation is a no-arg callable.

    def __init__(self, name: str) -> None:
        self.name = name
        # Initialize an empty operations registry.
        self.operations = {}

    def list_operations(self) -> List[str]:
        """
        Return the list of available operation labels in deterministic order.

        Returns:
            List[str]: human-readable operation names.
        """
        # Convert to list explicitly so the return type is concrete (not dict_keys).
        return list(self.operations.keys())

    def run(self, op_key: str) -> Optional[Any]:
        """
        Execute the operation identified by `op_key`.

        Behavior:
          - Validates that the operation exists in the provider's registry.
          - Invokes the registered callable with no arguments.
          - Returns the callable's result (if any).

        Args:
            op_key (str): Operation label as returned by `list_operations()`.

        Returns:
            Optional[Any]: The result returned by the operation (operations may return None).

        Raises:
            KeyError: If the requested operation key is not available.
        """
        if op_key not in self.operations:
            raise KeyError(f"Operation '{op_key}' is not available for {self.name}")

        # ✅ Correct dictionary lookup + callable invocation
        func = self.operations[op_key]
        return func()

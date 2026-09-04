from __future__ import annotations

from dataclasses import asdict, dataclass

from .model import canonical


class RegistryDenied(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityFamily:
    family_id: str
    display_name: str
    external_effects_possible: bool = True
    capital_possible: bool = False
    default_mode: str = "DRY_RUN"
    schema_version: str = "darwin.eco00.family.v1"

    def validate(self):
        if not self.family_id or not self.family_id.replace("_", "").isalnum() or self.family_id.lower() != self.family_id:
            raise RegistryDenied("invalid family id")
        if self.default_mode != "DRY_RUN":
            raise RegistryDenied("new capability families default to DRY_RUN")
        return self


class CapabilityRegistry:
    """Data registry: capability presence never grants execution permission."""

    def __init__(self, families=()):
        self._families = {}
        for family in families:
            self.register(family)

    def register(self, family: CapabilityFamily):
        family.validate()
        if family.family_id in self._families:
            raise RegistryDenied("duplicate capability family")
        self._families[family.family_id] = family

    def get(self, family_id: str) -> CapabilityFamily:
        try:
            return self._families[family_id]
        except KeyError as exc:
            raise RegistryDenied("unregistered capability family") from exc

    def records(self) -> list[dict]:
        return [asdict(self._families[key]) for key in sorted(self._families)]

    def snapshot(self) -> str:
        return canonical(self.records())


FAMILIES = (
    "freelance_services", "software_delivery", "micro_saas", "digital_products",
    "templates_and_assets", "translation_localization", "transcription_captioning",
    "research_and_data_services", "lead_generation", "content_and_media",
    "affiliate_referral", "ecommerce_owned_inventory", "wholesale_dropshipping",
    "print_on_demand", "cross_marketplace_resale", "marketplace_listing_management",
    "local_b2b_services", "authorized_bug_bounty", "automation_consulting",
    "data_cleanup_enrichment",
)


def default_capability_registry() -> CapabilityRegistry:
    capital = {"micro_saas", "ecommerce_owned_inventory", "wholesale_dropshipping",
               "print_on_demand", "cross_marketplace_resale"}
    return CapabilityRegistry(CapabilityFamily(item, item.replace("_", " ").title(),
                                               capital_possible=item in capital) for item in FAMILIES)

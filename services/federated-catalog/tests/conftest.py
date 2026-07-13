"""Shared fixtures for federated-catalog tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def sample_dcat_catalog() -> dict:
    """A minimal DCAT-AP JSON-LD catalogue response."""
    return {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "odrl": "http://www.w3.org/ns/odrl/2/",
        },
        "@type": "dcat:Catalog",
        "dcat:dataset": [
            {
                "@id": "https://example.com/datasets/weather",
                "@type": "dcat:Dataset",
                "dct:title": "Weather Features",
                "dct:description": "Hourly weather data",
                "dcat:keyword": ["weather", "gold"],
                "ds:accessLevel": "internal",
                "dcat:distribution": [
                    {
                        "@type": "dcat:Distribution",
                        "dcat:accessURL": {"@id": "https://api.example.com/query"},
                        "odrl:hasPolicy": {
                            "@type": "odrl:Offer",
                            "odrl:permission": [
                                {
                                    "odrl:action": {"@id": "odrl:use"},
                                    "odrl:constraint": [
                                        {
                                            "odrl:leftOperand": {"@id": "https://w3id.org/dsp/policy/Membership"},
                                            "odrl:operator": {"@id": "odrl:eq"},
                                            "odrl:rightOperand": {"@value": "active", "@type": "xsd:string"},
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                ],
            },
            {
                "@id": "https://example.com/datasets/meters",
                "@type": "dcat:Dataset",
                "dct:title": "Meter Readings",
                "dct:description": "15-minute meter data",
                "dcat:keyword": ["meters", "grid"],
                "ds:accessLevel": "restricted",
            },
        ],
    }


@pytest.fixture
def sample_dcat_secret_catalog() -> dict:
    """Catalogue with a secret dataset that should be skipped."""
    return {
        "@type": "dcat:Catalog",
        "dcat:dataset": [
            {
                "@id": "https://example.com/datasets/public",
                "dct:title": "Public Data",
                "ds:accessLevel": "open",
            },
            {
                "@id": "https://example.com/datasets/secret",
                "dct:title": "Secret Data",
                "ds:accessLevel": "secret",
            },
        ],
    }

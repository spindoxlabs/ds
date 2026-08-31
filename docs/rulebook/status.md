# Conformance status

**Generated. Do not edit.** `task rulebook:status` rewrites this file from `docs/blueprints/`, `docs/rulebook/`, the coverage manifest and the test sources. It is committed so that drift shows up in a diff.

Generated 2026-08-31 from `6166056`.

This page measures **linkage**, not correctness. A rule is *evidenced* when a test node names it — not when that node passes. Whether the suite is green is the runner's answer; see `docs/development/testing.md`. What this page can say, and no hand-written status can, is whether a claim has a runnable referent at all.

## Where the platform stands

| Measure | Count |
|---|--:|
| Blueprint requirement rows | 1623 |
| …of which binding (`must` + `should`) | 783 |
| …carrying a disposition | 252 |
| …answered by a **named rule** | 37 |
| …answered **at page level only** | 121 |
| …**unassessed** | 531 |
| Rulebook rules | 146 |
| …claiming enforcement (`Enforced` / `Partly enforced`) | 116 |
| …of those, **evidenced by a test that names them** | 116 |
| …of those, **unevidenced** | 0 |
| Test nodes declaring a rule | 788 |
| Structural problems | 0 |

**100% of the rules that claim enforcement can name a test.** That number is the one to move.

## Rules claiming enforcement with no test naming them

None. Every rule claiming enforcement names at least one test node.

## Every rule, by page

### `catalogue-and-metadata.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `C-1` | Enforced | ✅ evidenced | e2e×2 | `catalog-discovery`, `smoke` |
| `C-2` | Declared | · consistent | — | — |
| `C-3` | Enforced | ✅ evidenced | e2e×1, unit×4 | `catalog-discovery`, `services/federated-catalog/tests/test_registry_active.py::test_a_deactivated_participant_is_not_crawled`, `services/federated-catalog/tests/test_registry_active.py::test_the_request_asks_the_registry_to_filter_too` +2 more |
| `C-4` | Enforced | ✅ evidenced | unit×1 | `services/connector/tests/test_consumer_catalog_auth.py::test_catalog_accepts_the_crawler_and_names_no_person` |
| `C-5` | Enforced | ✅ evidenced | e2e×1, unit×2 | `uc3`, `libs/governance/tests/tests/test_mapper.py::test_odrl_offer_basic_structure`, `libs/governance/tests/tests/test_mapper.py::test_odrl_context_uses_profile_prefix` |
| `C-6` | Enforced | ✅ evidenced | unit×4 | `libs/governance/tests/tests/test_canonical_schema.py::test_purpose_is_read_from_the_canonical_location`, `libs/governance/tests/tests/test_mapper.py::test_purpose_comes_from_policy_declaration`, `libs/governance/tests/tests/test_mapper.py::test_tags_alone_produce_no_purpose_constraint` +1 more |
| `C-7` | Enforced | ✅ evidenced | e2e×1, unit×5 | `two-providers`, `libs/governance/tests/tests/test_dcat_shapes.py::TestDataService::test_serves_dataset_is_emitted_as_references`, `libs/governance/tests/tests/test_dcat_shapes.py::TestDataService::test_conforms_to_distinguishes_a_negotiable_endpoint` +3 more |
| `C-8` | Enforced | ✅ evidenced | unit×6 | `libs/governance/tests/tests/test_dcat_shapes.py::TestCatalogRecord::test_points_at_its_dataset_via_primary_topic`, `libs/governance/tests/tests/test_dcat_shapes.py::test_the_context_defines_foaf`, `services/federated-catalog/tests/test_dcat_shape.py::test_every_entry_carries_a_catalogue_record` +3 more |
| `C-9` | Enforced | ✅ evidenced | unit×10 | `libs/governance/tests/tests/test_compliance_checks.py::TestGovernanceFile::test_missing_file_is_an_error`, `libs/governance/tests/tests/test_compliance_checks.py::TestGovernanceFile::test_no_sources_is_an_error`, `libs/governance/tests/tests/test_compliance_checks.py::TestGovernanceFile::test_valid_file_passes_cleanly` +7 more |
| `C-10` | Enforced | ✅ evidenced | unit×13 | `libs/governance/tests/tests/test_compliance_checks.py::TestConsentCoherence::test_consent_required_without_filter_warns`, `libs/governance/tests/tests/test_compliance_checks.py::TestConsentCoherence::test_consent_required_with_filter_column_is_clean`, `libs/governance/tests/tests/test_compliance_checks.py::TestConsentCoherence::test_pii_without_row_filtering_warns` +10 more |
| `C-11` | Enforced | ✅ evidenced | unit×5 | `libs/governance/tests/tests/test_consent_checks.py::TestDatasetPurposes::test_empty_purpose_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestDatasetPurposes::test_absent_purpose_block_is_an_error`, `services/connector/tests/test_consent_vocabulary.py::TestPurposeEnforcement::test_empty_requested_purpose_is_denied_for_pii` +2 more |
| `C-12` | Enforced | ✅ evidenced | unit×3 | `libs/governance/tests/tests/test_compliance_evidence.py::TestDcatBlock::test_every_dcat_field_is_emitted`, `libs/governance/tests/tests/test_declared_not_enforced.py::test_a_dataset_missing_a_mandatory_dcat_property_fails`, `libs/governance/tests/tests/test_declared_not_enforced.py::test_a_complete_dataset_raises_no_dcat_ap_error` |
| `C-13` | Not enforced | · consistent | — | — |
| `C-14` | Enforced | ✅ evidenced | unit×3 | `libs/governance/tests/tests/test_compliance_checks.py::TestGovernanceFile::test_valid_file_passes_cleanly`, `libs/governance/tests/tests/test_declared_not_enforced.py::test_a_dataset_missing_a_mandatory_dcat_property_fails`, `libs/governance/tests/tests/test_declared_not_enforced.py::test_a_complete_dataset_raises_no_dcat_ap_error` |
| `C-15` | Enforced | ✅ evidenced | e2e×1, unit×3 | `user-authority`, `services/connector/tests/test_provider_api.py::test_provider_read_alone_can_list_agreements`, `services/connector/tests/test_provider_api.py::test_an_anonymous_caller_is_refused` +1 more |
| `C-16` | Enforced | ✅ evidenced | e2e×2, unit×11 | `uc2`, `user-authority`, `services/connector/tests/test_provider_api.py::test_another_participants_agreements_are_not_listed` +10 more |
| `C-17` | Enforced | ✅ evidenced | e2e×2, unit×12 | `api-contract`, `authz-perimeter`, `services/connector/tests/test_auth.py::test_internal_without_token_returns_401` +11 more |
| `C-18` | Enforced | ✅ evidenced | e2e×1 | `catalog-discovery` |
| `C-19` | Enforced | ✅ evidenced | e2e×1, unit×13 | `catalog-discovery`, `services/connector/tests/test_consumer_catalog_auth.py::test_catalog_without_any_credential_is_refused`, `services/connector/tests/test_consumer_catalog_auth.py::test_catalog_refuses_a_service_token_without_the_scope` +11 more |
| `C-20` | Enforced | ✅ evidenced | e2e×1, unit×4 | `authz-perimeter`, `services/connector/tests/test_consumer_catalog_auth.py::test_catalog_refuses_a_credential_linked_to_another_participant`, `services/connector/tests/test_dataplane_authorize.py::test_another_consumers_agreement_is_refused` +2 more |
| `C-21` | Partly enforced | ✅ evidenced | unit×5 | `libs/governance/tests/tests/test_mapper.py::test_access_requirements_all_no_membership_constraint`, `libs/governance/tests/tests/test_mapper.py::test_access_requirements_partner_adds_membership_constraint`, `libs/governance/tests/tests/test_mapper.py::test_internal_access_level_adds_membership_even_without_access_requirements` +2 more |

### `data-exchange.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `X-1` | Enforced | ✅ evidenced | e2e×2, unit×5 | `smoke`, `two-providers`, `libs/ds-edc/tests/test_protocol_pin.py::test_every_configured_dsp_address_carries_the_pinned_version` +4 more |
| `X-2` | Enforced | ✅ evidenced | unit×5 | `libs/ds-edc/tests/test_protocol_pin.py::test_the_version_is_derived_from_the_pin_and_not_written_twice`, `libs/ds-edc/tests/test_protocol_pin.py::test_the_pin_occurs_once_in_the_tree`, `libs/ds-edc/tests/test_protocol_pin.py::test_every_configured_dsp_address_carries_the_pinned_version` +2 more |
| `X-3` | Enforced | ✅ evidenced | e2e×1 | `smoke` |
| `X-4` | Enforced | ✅ evidenced | e2e×1, unit×3 | `smoke`, `services/connector/tests/test_auth.py::test_internal_without_token_returns_401`, `services/connector/tests/test_auth.py::test_internal_wrong_scope_returns_403` +1 more |
| `X-5` | Enforced | ✅ evidenced | e2e×1, unit×6 | `smoke`, `services/connector/tests/test_dataplane_authorize.py::test_consent_becomes_a_row_filter_spec`, `services/connector/tests/test_dataplane_authorize.py::test_open_dataset_needs_no_filter` +4 more |
| `X-6` | Enforced | ✅ evidenced | e2e×1, unit×3 | `fail-closed`, `services/connector/tests/test_dataplane_authorize.py::test_no_consent_yields_a_refusal_not_an_empty_filter`, `services/connector/tests/test_dataplane_authorize.py::test_unresolvable_subjects_deny` +1 more |
| `X-6b` | Enforced | ✅ evidenced | e2e×1, unit×2 | `fail-closed`, `services/connector/tests/test_internal_api.py::test_consent_check_no_consent`, `services/connector/tests/test_registry.py::test_http_registry_check_scope_error_returns_false` |
| `X-6c` | Enforced | ✅ evidenced | e2e×1, unit×5 | `fail-closed`, `services/connector/tests/test_dataplane_authorize.py::test_unknown_agreement_is_refused`, `services/connector/tests/test_dataplane_authorize.py::test_terminated_agreement_is_refused` +3 more |
| `X-7` | Declared | · consistent | — | — |
| `X-8` | Declared | · consistent | — | — |
| `X-9` | Enforced | ✅ evidenced | unit×6 | `services/connector/tests/test_dataplane_authorize.py::test_another_consumers_agreement_is_refused`, `services/connector/tests/test_dataplane_authorize.py::test_agreement_does_not_unlock_another_dataset`, `services/connector/tests/test_dataplane_authorize.py::test_unknown_agreement_is_refused` +3 more |
| `X-10` | Enforced | ✅ evidenced | unit×4 | `services/connector/tests/test_internal_api.py::test_agreement_status_unreachable_edc_is_not_a_404`, `services/connector/tests/test_internal_api.py::test_agreement_status_edc_5xx_is_not_a_404`, `services/connector/tests/test_internal_api.py::test_transfer_status_unreachable_edc_denies_and_says_so` +1 more |
| `X-11` | Enforced | ✅ evidenced | unit×1 | `services/connector/tests/test_pending_sweep.py::test_a_failed_termination_leaves_the_negotiation_for_the_next_pass` |
| `X-12` | Declared | · consistent | — | — |
| `X-13` | Partly enforced | ✅ evidenced | e2e×1 | `api-contract` |
| `X-14` | Declared | · consistent | — | — |
| `X-15` | Declared | · consistent | — | — |

### `data-models.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `M-1` | Enforced | ✅ evidenced | unit×3 | `libs/governance/tests/tests/test_canonical_schema.py::test_the_whole_dcat_block_survives_the_load`, `libs/governance/tests/tests/test_compliance_evidence.py::TestDcatBlock::test_every_dcat_field_is_emitted`, `libs/governance/tests/tests/test_compliance_evidence.py::TestDcatBlock::test_no_dcat_block_emits_no_empty_nodes` |
| `M-2` | Enforced | ✅ evidenced | unit×1 | `libs/governance/tests/tests/test_mapper.py::test_medallion_inference` |
| `M-3` | Enforced | ✅ evidenced | unit×4 | `libs/governance/tests/tests/test_mapper.py::test_odrl_context_uses_profile_prefix`, `libs/governance/tests/tests/test_mapper.py::test_profile_iri_included_in_context`, `services/connector/tests/test_ns_policy_profile.py::test_ns_policy_follows_a_profile_change_after_reset_caches` +1 more |
| `M-4` | Partly enforced | ✅ evidenced | e2e×1, unit×13 | `semantic-model`, `libs/governance/tests/test_semantic_model_contract.py::test_at_least_one_dataset_declares_its_payload_model`, `libs/governance/tests/test_semantic_model_contract.py::test_every_declared_model_is_served_by_this_participant` +11 more |
| `M-5` | Declared | · consistent | — | — |
| `M-6` | Enforced | ✅ evidenced | unit×3 | `libs/governance/tests/tests/test_compliance_checks.py::TestSemanticModel::test_declaring_no_model_is_not_a_finding`, `services/connector/tests/test_vocabulary_startup.py::test_no_shipped_vocabulary_needs_the_network_at_boot`, `services/connector/tests/test_vocabulary_startup.py::test_no_shipped_vocabulary_imposes_a_real_world_model` |
| `M-7` | Enforced | ✅ evidenced | e2e×1, unit×7 | `semantic-model`, `libs/governance/tests/test_semantic_model_contract.py::test_the_declaration_is_the_canonical_iri_and_is_shared_across_datasets`, `libs/governance/tests/tests/test_compliance_checks.py::TestSemanticModel::test_a_bare_name_is_an_error` +5 more |
| `M-8` | Enforced | ✅ evidenced | e2e×1, unit×10 | `semantic-model`, `libs/governance/tests/test_semantic_model_contract.py::test_every_declared_model_is_served_by_this_participant`, `libs/governance/tests/test_semantic_model_contract.py::test_a_participants_own_vocabulary_needs_no_network` +8 more |
| `M-9` | Enforced | ✅ evidenced | unit×5 | `libs/governance/tests/tests/test_schema_conformance.py::test_conforms_to_the_canonical_schema`, `libs/governance/tests/tests/test_schema_conformance.py::test_purpose_and_consent_live_where_the_schema_puts_them`, `libs/governance/tests/tests/test_schema_export.py::test_schemas_directory_exists` +2 more |
| `M-10` | Enforced | ✅ evidenced | unit×4 | `libs/governance/tests/tests/test_schema_export.py::test_purpose_vocabulary_lists_exactly_the_active_profile`, `libs/governance/tests/tests/test_schema_export.py::test_purpose_vocabulary_rejects_a_placeholder_term`, `services/connector/tests/test_ns_policy_profile.py::test_ns_policy_follows_a_profile_change_after_reset_caches` +1 more |
| `M-11` | Partly enforced | ✅ evidenced | unit×5 | `services/connector/tests/test_ns_vocabularies.py::test_the_index_lists_every_surface`, `services/connector/tests/test_ns_vocabularies.py::test_the_index_reports_which_copies_are_missing`, `services/connector/tests/test_ns_vocabularies.py::test_the_registry_projection_carries_the_iri` +2 more |
| `M-12` | Declared | · consistent | — | — |
| `M-13` | Enforced | ✅ evidenced | unit×8 | `libs/governance/tests/tests/test_consent_checks.py::TestPurposeTaxonomy::test_unresolvable_broader_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestPurposeTaxonomy::test_broader_cycle_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestPurposeTaxonomy::test_unknown_skos_relation_is_an_error` +5 more |
| `M-14` | Declared | · consistent | — | — |
| `M-15` | Declared | · consistent | — | — |

### `participation.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `P-1` | Enforced | ✅ evidenced | e2e×1, unit×11 | `org-onboarding`, `services/identity-registry/tests/test_agreements_current.py::test_owner_without_an_accepted_agreement_is_not_found`, `services/identity-registry/tests/test_agreements_current.py::test_owner_not_verified_is_not_found` +9 more |
| `P-2` | Enforced | ✅ evidenced | e2e×1, integration×1, unit×1 | `org-onboarding`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_the_credential_is_signed_by_the_trust_anchor`, `services/identity-registry/tests/test_org_onboarding.py::test_full_lifecycle_and_suspend` |
| `P-3` | Enforced | ✅ evidenced | e2e×1, integration×1, unit×2 | `dcp-trust`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_the_presentation_carries_the_membership_credential`, `services/identity-registry/tests/test_api.py::test_issue_membership_credential` +1 more |
| `P-4` | Enforced | ✅ evidenced | e2e×1, unit×9 | `org-onboarding`, `services/connector/tests/test_consent_provisioning.py::test_admin_shares_is_idempotent`, `services/identity-registry/tests/test_cip_conformance.py::test_bootstrapping_again_republishes_the_service_entry` +7 more |
| `P-5` | Declared | · consistent | — | — |
| `P-6` | Enforced | ✅ evidenced | integration×2, unit×10 | `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_each_registry_publishes_its_did_at_the_well_known_path`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_the_published_document_carries_a_usable_key`, `services/identity-registry/tests/test_auth.py::test_public_did_without_auth` +9 more |
| `P-7` | Enforced | ✅ evidenced | unit×11 | `services/identity-registry/tests/test_custody.py::test_an_anchor_holding_only_its_own_key_is_clean`, `services/identity-registry/tests/test_custody.py::test_an_enrolled_participants_public_key_is_not_custody`, `services/identity-registry/tests/test_custody.py::test_a_participant_instance_holds_its_own` +8 more |
| `P-8` | Enforced | ✅ evidenced | e2e×1, integration×2, unit×10 | `dcp-trust`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_a_verifier_with_a_grant_is_served`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_a_self_issued_token_without_a_grant_is_refused` +10 more |
| `P-8a` | Enforced | ✅ evidenced | e2e×1, integration×1, unit×10 | `dcp-trust`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_an_unreachable_did_document_is_refused`, `services/identity-registry/tests/test_dcp_auth.py::test_unpublished_verifier_is_rejected` +9 more |
| `P-8b` | Enforced | ✅ evidenced | integration×1, unit×4 | `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_the_status_list_is_served_signed_by_default`, `services/identity-registry/tests/test_status_list.py::test_build_status_list_credential`, `services/identity-registry/tests/test_status_list.py::test_encoded_list_is_gzip_not_zlib` +2 more |
| `P-8c` | Enforced | ✅ evidenced | unit×9 | `libs/ds-auth/tests/test_user_credentials.py::test_a_credential_verifies_against_the_published_key`, `libs/ds-auth/tests/test_user_credentials.py::test_a_signature_from_another_key_is_refused`, `libs/ds-auth/tests/test_user_credentials.py::test_an_unreachable_issuer_fails_closed` +6 more |
| `P-9` | Enforced | ✅ evidenced | unit×7 | `services/identity-registry/tests/test_status_list_allocation.py::test_two_membership_credentials_get_distinct_indices`, `services/identity-registry/tests/test_status_list_allocation.py::test_indices_do_not_collide_across_credential_types`, `services/identity-registry/tests/test_status_list_allocation.py::test_many_issuances_are_all_distinct` +4 more |
| `P-10` | Enforced | ✅ evidenced | unit×3 | `services/identity-registry/tests/test_status_list_allocation.py::test_issuance_leaves_the_revocation_bit_clear`, `services/identity-registry/tests/test_status_list_allocation.py::test_the_register_is_empty_until_something_is_revoked`, `services/identity-registry/tests/test_status_list_allocation.py::test_revoking_one_credential_does_not_revoke_the_other` |
| `P-11` | Enforced | ✅ evidenced | unit×12 | `libs/ds-auth/tests/test_user_credentials.py::test_a_signature_from_another_key_is_refused`, `libs/ds-auth/tests/test_user_credentials.py::test_no_issuer_and_no_insecure_flag_is_a_503`, `libs/ds-auth/tests/test_verify.py::test_verifies_valid_token` +9 more |
| `P-12` | Enforced | ✅ evidenced | unit×6 | `services/federated-catalog/tests/test_registry_active.py::test_a_deactivated_participant_is_not_crawled`, `services/federated-catalog/tests/test_registry_active.py::test_the_request_asks_the_registry_to_filter_too`, `services/identity-registry/tests/test_api.py::test_list_participants` +3 more |
| `P-12a` | Enforced | ✅ evidenced | unit×5 | `services/identity-registry/tests/test_trust_list.py::test_the_list_is_public`, `services/identity-registry/tests/test_trust_list.py::test_every_entry_names_where_its_key_resolves`, `services/identity-registry/tests/test_trust_list.py::test_the_anchor_lists_itself_after_bootstrap` +2 more |
| `P-12b` | Enforced | ✅ evidenced | unit×3 | `services/identity-registry/tests/test_trust_list.py::test_an_entry_with_no_scope_is_refused`, `services/identity-registry/tests/test_trust_list.py::test_a_trust_service_provider_must_name_its_authority`, `services/identity-registry/tests/test_trust_list.py::test_a_provider_derives_authority_and_says_so` |
| `P-12c` | Enforced | ✅ evidenced | unit×3 | `services/identity-registry/tests/test_trust_list.py::test_a_revoked_issuer_stays_in_the_list`, `services/identity-registry/tests/test_trust_list.py::test_revocation_requires_a_reason`, `services/identity-registry/tests/test_trust_list.py::test_an_unknown_issuer_cannot_be_revoked` |
| `P-13` | Enforced | ✅ evidenced | integration×1, unit×1 | `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_every_named_status_list_url_is_fetchable`, `services/identity-registry/tests/test_auth.py::test_public_status_without_auth` |
| `P-14` | Enforced | ✅ evidenced | unit×8 | `services/identity-registry/tests/test_conformity.py::test_an_expired_credential_is_not_a_held_credential`, `services/identity-registry/tests/test_conformity.py::test_a_superseded_agreement_version_is_non_conformant`, `services/identity-registry/tests/test_conformity.py::test_never_accepting_the_agreement_is_reported_differently` +5 more |
| `P-15` | Declared | · consistent | — | — |
| `P-16` | Enforced | ✅ evidenced | unit×6 | `services/identity-registry/tests/test_api.py::test_revoke_credential`, `services/identity-registry/tests/test_credential_check.py::test_a_revoked_credential_is_not_held`, `services/identity-registry/tests/test_presentation_scope.py::test_a_revoked_credential_is_never_presented` +3 more |
| `P-17` | Declared | · consistent | — | — |
| `P-18` | Enforced | ✅ evidenced | e2e×1 | `consent-withdrawal` |
| `P-19` | Declared | · consistent | — | — |
| `P-20` | Enforced | ✅ evidenced | unit×8 | `services/identity-registry/tests/test_enrolment.py::test_enrolment_registers_the_did_the_key_and_the_endpoints`, `services/identity-registry/tests/test_enrolment.py::test_the_anchor_stores_the_public_key_and_no_private_key`, `services/identity-registry/tests/test_enrolment.py::test_a_valid_code_without_a_matching_signature_enrols_nothing` +5 more |
| `P-21` | Enforced | ✅ evidenced | unit×7 | `services/identity-registry/tests/test_cip_conformance.py::test_the_acknowledgement_is_a_conformant_credential_status`, `services/identity-registry/tests/test_cip_conformance.py::test_the_delivered_message_is_a_conformant_credential_message`, `services/identity-registry/tests/test_enrolment.py::test_endpoints_come_from_the_did_document_not_the_request` +4 more |
| `P-22` | Enforced | ✅ evidenced | e2e×1, unit×5 | `dcp-trust`, `services/identity-registry/tests/test_cip_conformance.py::test_issuer_metadata_is_conformant`, `services/identity-registry/tests/test_cip_conformance.py::test_the_anchor_publishes_an_issuer_service_entry` +3 more |
| `P-23` | Enforced | ✅ evidenced | unit×9 | `services/identity-registry/tests/test_conformity.py::test_criteria_are_read_from_a_file`, `services/identity-registry/tests/test_conformity.py::test_a_missing_criteria_file_is_an_error`, `services/identity-registry/tests/test_conformity.py::test_an_empty_criteria_file_is_an_error` +6 more |
| `P-24` | Enforced | ✅ evidenced | unit×2 | `services/identity-registry/tests/test_conformity.py::test_a_deactivated_participant_is_reported_not_skipped`, `services/identity-registry/tests/test_conformity.py::test_a_participant_no_criterion_covers_is_a_finding` |
| `P-25` | Enforced | ✅ evidenced | e2e×1, integration×1, unit×12 | `org-onboarding`, `services/identity-registry/tests/integration/test_dcp_roundtrip.py::test_a_presented_credential_names_both_registers`, `services/identity-registry/tests/test_org_onboarding.py::test_full_lifecycle_and_suspend` +11 more |
| `P-26` | Enforced | ✅ evidenced | e2e×1, unit×6 | `org-onboarding`, `services/identity-registry/tests/test_suspension.py::test_a_suspension_bit_is_the_only_bit_that_can_be_cleared`, `services/identity-registry/tests/test_suspension.py::test_clearing_a_bit_cannot_reach_the_revocation_register` +4 more |

### `personal-data.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `D-1` | Declared | · consistent | — | — |
| `D-2` | Enforced | ✅ evidenced | unit×7 | `services/connector/tests/test_access_request_declaration.py::test_justification_ref_rejects_an_email`, `services/connector/tests/test_access_request_declaration.py::test_justification_ref_accepts_an_opaque_reference`, `services/connector/tests/test_acting_principal.py::test_the_act_names_a_human_pseudonymously` +4 more |
| `D-3` | Declared | · consistent | — | — |
| `D-4` | Enforced | ✅ evidenced | unit×2 | `services/connector/tests/test_consent_vocabulary.py::TestSharingOffersEndpoint::test_contract_based_offer_is_flagged_as_disclosure`, `services/connector/tests/test_consent_vocabulary.py::TestOfferDrivenShares::test_contract_based_offer_cannot_be_toggled` |
| `D-5` | Enforced | ✅ evidenced | e2e×3, unit×3 | `chain-partner`, `chain-unbundling`, `uc1` +3 more |
| `D-6` | Declared | · consistent | — | — |
| `D-7` | Enforced | ✅ evidenced | unit×10 | `libs/governance/tests/tests/test_consent_checks.py::TestDatasetPurposes::test_empty_purpose_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestDatasetPurposes::test_absent_purpose_block_is_an_error`, `services/connector/tests/test_consent_ask_projection.py::test_open_dataset_is_never_a_question` +7 more |
| `D-8` | Enforced | ✅ evidenced | e2e×1, unit×8 | `consent-purpose`, `services/connector/tests/test_access_request_declaration.py::test_declared_purpose_within_the_offer_is_accepted`, `services/connector/tests/test_access_request_declaration.py::test_narrower_purpose_than_the_offer_names_is_accepted` +6 more |
| `D-9` | Enforced | ✅ evidenced | e2e×1, unit×3 | `consent-purpose`, `libs/governance/tests/tests/test_consent_checks.py::TestSharingOffers::test_broader_declaration_does_not_satisfy_a_narrower_offer`, `services/connector/tests/test_access_request_declaration.py::test_broader_purpose_than_the_offer_permits_is_refused` +1 more |
| `D-10` | Enforced | ✅ evidenced | e2e×1, unit×11 | `consent-purpose`, `libs/governance/tests/tests/test_consent_checks.py::TestDatasetPurposes::test_unknown_declared_purpose_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestDatasetPurposes::test_full_iri_declaration_is_accepted` +9 more |
| `D-11` | Enforced | ✅ evidenced | e2e×3, unit×11 | `chain-community`, `chain-unbundling`, `uc2` +11 more |
| `D-11a` | Enforced | ✅ evidenced | e2e×1, unit×5 | `chain-unbundling`, `libs/governance/tests/tests/test_consent_checks.py::TestSharingOffers::test_a_controller_role_with_no_declared_vocabulary_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestSharingOffers::test_a_controller_role_outside_the_declared_vocabulary_is_an_error` +3 more |
| `D-12` | Enforced | ✅ evidenced | unit×8 | `libs/governance/tests/tests/test_consent_checks.py::TestSharingOffers::test_missing_consent_text_version_is_an_error`, `services/connector/tests/test_consent_provisioning.py::test_legal_basis_surfaces_in_internal_check`, `services/connector/tests/test_consent_provisioning.py::test_subject_offer_share_records_legal_basis` +5 more |
| `D-13` | Enforced | ✅ evidenced | e2e×1, unit×10 | `onboarding-seam`, `libs/governance/tests/tests/test_consent_checks.py::TestSharingOffers::test_missing_consent_text_version_is_an_error`, `services/connector/tests/test_offer_drift.py::test_no_recorded_consent_is_never_drift` +8 more |
| `D-14` | Enforced | ✅ evidenced | e2e×3, unit×18 | `chain-community`, `chain-partner`, `uc1` +18 more |
| `D-15` | Enforced | ✅ evidenced | unit×16 | `services/connector/tests/test_consent_provisioning.py::test_specific_revoke_overrides_wildcard`, `services/connector/tests/test_consent_provisioning.py::test_specific_grant_authorises_without_wildcard`, `services/connector/tests/test_consent_provisioning.py::test_withdrawing_one_offer_leaves_the_other_granted` +13 more |
| `D-16` | Enforced | ✅ evidenced | unit×4 | `services/connector/tests/test_acting_principal.py::test_the_owner_acted_for_is_recorded`, `services/connector/tests/test_acting_principal.py::test_ingestion_attributes_the_verified_caller_not_the_body`, `services/connector/tests/test_consumer_catalog_auth.py::test_catalog_rejects_a_bare_subject_header` +1 more |
| `D-17` | Enforced | ✅ evidenced | e2e×1 | `consent-withdrawal` |
| `D-18` | Enforced | ✅ evidenced | e2e×1, unit×11 | `consent-request`, `services/connector/tests/test_consent_ask_projection.py::test_consent_gated_dataset_asks_when_capacity_is_unprovable`, `services/connector/tests/test_consent_ask_projection.py::test_pending_ask_is_reported_so_a_retry_reattaches` +9 more |
| `D-19` | Enforced | ✅ evidenced | e2e×1, unit×5 | `consent-request`, `services/connector/tests/test_authorizations.py::test_authorizations_empty`, `services/connector/tests/test_authorizations.py::test_authorizations_returns_granted` +3 more |
| `D-20` | Enforced | ✅ evidenced | e2e×1, unit×11 | `authz-perimeter`, `services/connector/tests/test_auth.py::test_consent_check_requires_scope`, `services/connector/tests/test_consent_provisioning.py::test_admin_shares_requires_provision_scope` +9 more |
| `D-21` | Enforced | ✅ evidenced | e2e×1, unit×9 | `uc1`, `services/connector/tests/test_circle_admission.py::test_it_asks_the_narrow_check_not_the_roster`, `services/connector/tests/test_circle_admission.py::test_the_credential_type_reaches_the_registry` +7 more |
| `D-22` | Enforced | ✅ evidenced | unit×3 | `services/identity-registry/tests/test_did.py::test_user_did_document_no_auth`, `services/identity-registry/tests/test_did.py::test_the_did_path_route_does_not_shadow_dids`, `services/identity-registry/tests/test_did.py::test_path_form_resolves_a_user_did` |
| `D-22a` | Enforced | ✅ evidenced | unit×2 | `services/identity-registry/tests/test_custody.py::test_the_credential_records_who_attested_the_person`, `services/identity-registry/tests/test_did.py::test_path_form_resolves_a_user_did` |
| `D-22b` | Enforced | ✅ evidenced | unit×5 | `services/identity-registry/tests/test_identifier_cascade.py::test_the_continuity_key_wins_over_a_changed_email`, `services/identity-registry/tests/test_identifier_cascade.py::test_a_recycled_identifier_is_quarantined`, `services/identity-registry/tests/test_identifier_cascade.py::test_derivation_happens_only_when_every_rung_misses` +2 more |

### `policies.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `A-1` | Enforced | ✅ evidenced | e2e×1, unit×7 | `consent-purpose`, `libs/governance/tests/tests/test_consent_checks.py::TestPurposeTaxonomy::test_unresolvable_broader_is_an_error`, `libs/governance/tests/tests/test_consent_checks.py::TestPurposeTaxonomy::test_broader_cycle_is_an_error` +5 more |
| `A-2` | Enforced | ✅ evidenced | e2e×1, unit×4 | `consent-purpose`, `libs/governance/tests/tests/test_consent_checks.py::TestSharingOffers::test_broader_declaration_does_not_satisfy_a_narrower_offer`, `libs/governance/tests/tests/test_models.py::test_default_profile_roots_are_not_mutually_reachable` +2 more |
| `A-3` | Declared | · consistent | — | — |
| `A-4` | Enforced | ✅ evidenced | integration×2, unit×3 | `services/identity-registry/tests/integration/test_governance_runtime_validation.py::test_the_owner_participant_check_has_something_to_compare`, `services/identity-registry/tests/integration/test_governance_runtime_validation.py::test_an_unreadable_registry_is_refused_not_skipped`, `libs/governance/tests/tests/test_compliance_checks.py::TestOwners::test_owner_did_not_a_participant_warns` +2 more |
| `A-5` | Enforced | ✅ evidenced | unit×5 | `libs/governance/tests/tests/test_compliance_checks.py::TestIdentifierCollisions::test_keys_differing_only_by_separator_collide`, `libs/governance/tests/tests/test_compliance_checks.py::TestIdentifierCollisions::test_explicit_duplicate_asset_ids_collide`, `libs/governance/tests/tests/test_compliance_checks.py::TestIdentifierCollisions::test_distinct_keys_do_not_collide` +2 more |
| `A-6` | Enforced | ✅ evidenced | unit×2 | `libs/governance/tests/tests/test_compliance_checks.py::TestGovernanceFile::test_secret_datasets_are_not_exposed`, `libs/governance/tests/tests/test_mapper.py::test_secret_level_no_permissions` |
| `A-7` | Enforced | ✅ evidenced | unit×1 | `libs/governance/tests/tests/test_mapper.py::test_pii_prohibits_transfer_and_sublicense` |
| `A-8` | Enforced | ✅ evidenced | unit×4 | `libs/governance/tests/tests/test_mapper.py::test_retention_days_adds_delete_obligation_with_delay_period`, `libs/governance/tests/tests/test_mapper.py::test_attribution_obligation_uses_attribute_to`, `libs/governance/tests/tests/test_mapper.py::test_rdf_is_declared_when_an_obligation_uses_it` +1 more |
| `A-9` | Not enforced | · consistent | — | — |
| `A-10` | Enforced | ✅ evidenced | e2e×1, unit×8 | `uc3`, `libs/governance/tests/tests/test_mapper.py::test_open_level_permits_transfer`, `libs/governance/tests/tests/test_mapper.py::test_restricted_level_only_query` +6 more |
| `A-11` | Enforced | ✅ evidenced | e2e×1, java×30 | `fail-closed`, `ConnectorClientTest#aRequestThatCannotBeSignedIsNotSent`, `ConnectorClientTest#postingAlsoRefusesToSendUnsigned` +28 more |
| `A-12` | Enforced | ✅ evidenced | e2e×1, java×10 | `consent-withdrawal`, `FailClosedTest#sustainedSilenceTerminates`, `FailClosedTest#aDefiniteNoStillTerminatesImmediately` +8 more |
| `A-13` | Declared | · consistent | — | — |
| `A-14` | Enforced | ✅ evidenced | java×7 | `PolicyRegistrationTest#consentStaysBoundInEveryScope`, `PolicyRegistrationTest#consentHasAFunctionForBothOperandFormsInEveryScope`, `PolicyRegistrationTest#everyBoundOperandHasAFunctionSomewhere` +4 more |
| `CR-1` | — | · precedence | — | — |
| `CR-2` | — | · precedence | — | — |
| `CR-3` | — | · precedence | — | — |
| `CR-4` | — | · precedence | — | — |
| `CR-5` | — | · precedence | — | — |

### `provenance-and-logging.md`

| Rule | Claimed | Verdict | Layers | Evidence |
|---|---|---|---|---|
| `L-1` | Enforced | ✅ evidenced | unit×4 | `services/connector/tests/test_prov_bridge_emitters.py::test_the_scan_finds_the_emitters`, `services/connector/tests/test_prov_bridge_emitters.py::test_every_emitter_has_a_call_site`, `services/connector/tests/test_prov_bridge_emitters.py::test_every_emitted_type_is_a_rulebook_type` +1 more |
| `L-1a` | Enforced | ✅ evidenced | unit×1 | `services/connector/tests/test_prov_bridge_emitters.py::test_the_unemitted_types_are_exactly_the_declared_ones` |
| `L-2` | Enforced | ✅ evidenced | e2e×1, unit×18 | `onboarding-seam`, `services/connector/tests/test_consent_provisioning.py::test_declining_one_offer_does_not_erase_a_grant_on_another`, `services/connector/tests/test_provenance_events.py::test_disclosure_computes_the_snapshot_the_caller_cannot` +16 more |
| `L-3` | Enforced | ✅ evidenced | unit×4 | `services/connector/tests/test_acting_principal.py::test_the_act_names_a_human_pseudonymously`, `services/connector/tests/test_acting_principal.py::test_no_personal_data_reaches_the_record`, `services/provenance/tests/test_event_agents.py::test_the_subject_edge_is_distinguishable_from_the_two_parties` +1 more |
| `L-4` | Enforced | ✅ evidenced | e2e×1, unit×9 | `onboarding-seam`, `services/connector/tests/test_provenance_events.py::test_disclosure_by_offer_keys_each_event_distinctly`, `services/provenance/tests/test_event_idempotency.py::test_an_event_without_an_id_is_stored_once` +7 more |
| `L-5` | Enforced | ✅ evidenced | e2e×1, unit×10 | `lineage`, `services/provenance/tests/test_event_agents.py::test_access_revoked_names_the_subject_as_an_agent`, `services/provenance/tests/test_event_agents.py::test_the_subject_edge_is_distinguishable_from_the_two_parties` +8 more |
| `L-6` | Declared | · consistent | — | — |
| `L-7` | Enforced | ✅ evidenced | unit×4 | `services/provenance/tests/test_relation_vocabulary.py::test_every_written_relation_is_accepted_by_the_relations_route`, `services/provenance/tests/test_relation_vocabulary.py::test_every_written_relation_is_defined_in_the_context`, `services/provenance/tests/test_relation_vocabulary.py::test_every_accepted_relation_is_defined_in_the_context` +1 more |
| `L-8` | Enforced | ✅ evidenced | unit×5 | `services/provenance/tests/test_jsonld_service.py::test_endpoints_are_keyed_by_the_nodes_own_type`, `services/provenance/tests/test_jsonld_service.py::test_an_agent_endpoint_is_an_agent_not_an_activity`, `services/provenance/tests/test_jsonld_service.py::test_a_same_type_edge_keeps_both_ends_and_stays_directional` +2 more |
| `L-9` | Declared | · consistent | — | — |
| `L-10` | Enforced | ✅ evidenced | e2e×1, unit×4 | `authz-perimeter`, `services/provenance/tests/test_auth.py::test_write_without_token_returns_401`, `services/provenance/tests/test_auth.py::test_read_without_token_returns_401` +2 more |
| `L-11` | Enforced | ✅ evidenced | unit×2 | `services/provenance/tests/test_events_query.py::test_my_events_needs_a_credential`, `services/provenance/tests/test_events_query.py::test_my_events_rejects_a_read_scope_alone` |
| `L-12` | Enforced | ✅ evidenced | e2e×1, unit×9 | `lineage`, `services/provenance/tests/test_audit_log.py::test_a_query_event_writes_a_compliance_row`, `services/provenance/tests/test_audit_log.py::test_the_summary_counts_real_queries` +7 more |
| `L-13` | Enforced | ✅ evidenced | unit×8 | `services/connector/tests/test_provenance_events.py::test_ingestion_requires_scope`, `services/connector/tests/test_provenance_events.py::test_disclosure_requires_its_own_scope`, `services/provenance/tests/test_auth.py::test_write_without_token_returns_401` +5 more |
| `L-14` | Declared | · consistent | — | — |
| `L-15` | Enforced | ✅ evidenced | unit×4 | `services/connector/tests/test_prov_bridge_emitters.py::test_the_scan_finds_the_emitters`, `services/connector/tests/test_prov_bridge_emitters.py::test_every_emitter_has_a_call_site`, `services/provenance/tests/test_events.py::test_an_unknown_event_type_is_refused` +1 more |
| `L-16` | Declared | · consistent | — | — |

## Blueprint coverage

Every binding blueprint row and what answers it. `may` and `recommended` rows are counted below but never demand a disposition — declining an optional row owes nobody an explanation, silently dropping a `must` owes everybody one.

| Prefix | Binding rows | covered | open | out-of-scope | unassessed |
|---|--:|--:|--:|--:|--:|
| `CEEDS-ARC` | 7 | 0 | 0 | 0 | 7 |
| `CEEDS-BUC` | 54 | 0 | 0 | 0 | 54 |
| `CEEDS-CON` | 6 | 0 | 0 | 0 | 6 |
| `CEEDS-GOV` | 3 | 0 | 0 | 0 | 3 |
| `CEEDS-IMP` | 28 | 0 | 0 | 0 | 28 |
| `CEEDS-INT` | 22 | 1 | 0 | 1 | 20 |
| `CEEDS-STD` | 4 | 2 | 0 | 1 | 1 |
| `DSSC-AUP` | 28 | 20 | 3 | 0 | 5 |
| `DSSC-BIZ` | 314 | 1 | 0 | 0 | 313 |
| `DSSC-CDP` | 1 | 0 | 0 | 0 | 1 |
| `DSSC-DEX` | 47 | 23 | 1 | 7 | 16 |
| `DSSC-DMO` | 25 | 7 | 2 | 1 | 15 |
| `DSSC-DSO` | 25 | 9 | 3 | 1 | 12 |
| `DSSC-FND` | 7 | 0 | 0 | 0 | 7 |
| `DSSC-IAM` | 12 | 12 | 0 | 0 | 0 |
| `DSSC-PTO` | 39 | 26 | 9 | 0 | 4 |
| `DSSC-PUB` | 36 | 32 | 2 | 0 | 2 |
| `DSSC-SVD` | 14 | 5 | 0 | 0 | 9 |
| `DSSC-TRF` | 15 | 11 | 0 | 0 | 4 |
| `DSSC-VCS` | 58 | 0 | 0 | 58 | 0 |
| `DSSC-XCT` | 38 | 9 | 0 | 5 | 24 |

Non-binding rows not shown above: 840 (138 recommended, 177 may, 525 informative).

### Rows answered by a named rule

The strong form: the row inherits its rule's verdict, so a rule nothing tests makes the row visibly unanswered rather than quietly done.

| Requirement | Force | Rules | From | Every rule evidenced? |
|---|---|---|---|---|
| `DSSC-AUP-08` | must | `A-13` | manifest | n/a — declared |
| `DSSC-AUP-51` | must | `CR-1` | manifest | n/a — declared |
| `DSSC-AUP-52` | must | `CR-3` | manifest | n/a — declared |
| `DSSC-AUP-53` | must | `CR-2` | manifest | n/a — declared |
| `DSSC-BIZ-143` | must | `P-12a` | rule text | yes |
| `DSSC-DEX-36` | must | `X-4` | manifest | yes |
| `DSSC-DMO-23` | should | `M-11` | manifest | yes |
| `DSSC-DSO-11` | must | `C-12` | manifest | yes |
| `DSSC-DSO-13` | must | `C-14` | manifest | yes |
| `DSSC-IAM-06` | must | `P-6`, `P-7`, `P-8`, `P-21` | manifest | yes |
| `DSSC-IAM-07` | must | `P-8`, `P-8a`, `P-21` | manifest | yes |
| `DSSC-IAM-08` | must | `P-3` | manifest | yes |
| `DSSC-IAM-13` | must | `P-20`, `P-8` | manifest | yes |
| `DSSC-IAM-14` | must | `P-5` | manifest | n/a — declared |
| `DSSC-IAM-29` | must | `P-6`, `P-7`, `P-20`, `P-21` | manifest | yes |
| `DSSC-PTO-40` | must | `L-1` | manifest | yes |
| `DSSC-PTO-41` | must | `L-1` | manifest | yes |
| `DSSC-PTO-59` | must | `L-9` | manifest | n/a — declared |
| `DSSC-PTO-79` | must | `L-12` | manifest | yes |
| `DSSC-PUB-05` | must | `C-1` | manifest | yes |
| `DSSC-PUB-13` | must | `C-15` | manifest | yes |
| `DSSC-PUB-14` | must | `C-16` | manifest | yes |
| `DSSC-PUB-19` | must | `C-17` | manifest | yes |
| `DSSC-PUB-23` | must | `C-17` | manifest | yes |
| `DSSC-PUB-25` | must | `C-18` | manifest | yes |
| `DSSC-PUB-26` | must | `C-17` | manifest | yes |
| `DSSC-PUB-27` | must | `C-19` | manifest | yes |
| `DSSC-PUB-32` | must | `C-20` | manifest | yes |
| `DSSC-PUB-38` | must | `C-5` | manifest | yes |
| `DSSC-PUB-41` | must | `C-7` | manifest | yes |
| `DSSC-SVD-30` | must | `P-8`, `P-20`, `P-21`, `P-22` | manifest | yes |
| `DSSC-TRF-02` | must | `P-23` | manifest | yes |
| `DSSC-TRF-04` | must | `P-25` | manifest | yes |
| `DSSC-TRF-05` | must | `P-12`, `P-12a` | manifest | yes |
| `DSSC-TRF-19` | informative | `P-12b` | rule text | yes |
| `DSSC-TRF-21` | informative | `P-12b` | rule text | yes |
| `DSSC-TRF-38` | must | `P-14` | rule text | yes |
| `DSSC-TRF-41` | must | `P-6`, `P-7`, `P-8`, `P-21` | manifest | yes |
| `DSSC-XCT-07` | must | `D-6` | manifest | n/a — declared |

### Rows answered only at page level

125 rows. A rulebook page addresses the topic and nobody has said which rule answers the row, so no evidence attaches and none of these can read as done. This is the granularity the rulebook's own *Blueprint rows* sections have; sharpening one to a named rule is the work.

| Requirement | Force | Page | Requirement text |
|---|---|---|---|
| `CEEDS-INT-23` | informative | [data-exchange](data-exchange.md) | The dataspace protocol outlines how transfer metadata is provisioned, including dataset d… |
| `CEEDS-INT-25` | must | [data-exchange](data-exchange.md) | The dataspace protocol ensures fundamental technical interoperability for participants, a… |
| `CEEDS-INT-26` | informative | [data-exchange](data-exchange.md) | The dataspace protocol defines the minimum standard of communication so that each actor m… |
| `CEEDS-STD-10` | recommended | [catalogue-and-metadata](catalogue-and-metadata.md) | DCAT (Data Catalog Vocabulary) is recommended as a publisher to describe datasets and dat… |
| `CEEDS-STD-13` | should | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue follows as much as possible the FAIR (Findable, Accessible, Interoperable,… |
| `CEEDS-STD-14` | informative | [catalogue-and-metadata](catalogue-and-metadata.md) | An example of a centralized or distributed catalogue implementation could be the Metadata… |
| `CEEDS-STD-19` | must | [data-exchange](data-exchange.md) | The dataspace protocol ensures fundamental technical interoperability for participants, a… |
| `DSSC-AUP-01` | must | [policies](policies.md) | A data space must be able to convert business rules into machine-readable policies. |
| `DSSC-AUP-02` | must | [policies](policies.md) | A data space must be able to validate the syntax of policies before deployment. |
| `DSSC-AUP-03` | must | [policies](policies.md) | A data space must be able to validate the semantics of policies before deployment. |
| `DSSC-AUP-04` | must | [policies](policies.md) | All policies must be enforced during the publication of data products in a catalogue serv… |
| `DSSC-AUP-05` | must | [policies](policies.md) | All policies must be enforced during discovery. |
| `DSSC-AUP-07` | must | [policies](policies.md) | All policies must be enforced during the actual sharing of the data. |
| `DSSC-AUP-09` | must | [policies](policies.md) | Policies must be expressed in machine-readable formats. |
| `DSSC-AUP-10` | must | [policies](policies.md) | Each policy must include metadata describing its language. |
| `DSSC-AUP-11` | must | [policies](policies.md) | Each policy must include metadata describing its serialization format. |
| `DSSC-AUP-12` | must | [policies](policies.md) | Each policy must include metadata describing its profile. |
| `DSSC-AUP-13` | must | [policies](policies.md) | Each policy must include metadata describing its version. |
| `DSSC-AUP-16` | must | [policies](policies.md) | Participant agents containing a control plane, in which policy negotiation and execution… |
| `DSSC-AUP-17` | must | [policies](policies.md) | Trust services able to validate/verify claims, so that policy evaluation and execution ca… |
| `DSSC-AUP-39` | must | [policies](policies.md) | The data space must decide on / define its policy interpretation rules. |
| `DSSC-AUP-44` | must | [policies](policies.md) | The profile defines standard vocabulary for the domain (source: "Required elements"). |
| `DSSC-AUP-50` | must | [policies](policies.md) | The data space must specify conflict resolution rules. |
| `DSSC-DEX-01` | must | [data-exchange](data-exchange.md) | The outcome of a data space's strategic choices about how protocols for data exchange are… |
| `DSSC-DEX-02` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | A data provider must describe the technical means to access the data, such as application… |
| `DSSC-DEX-08` | must | [data-exchange](data-exchange.md) | A choice for the associated transmission method needs to be made (e.g. HTTP, Event Stream… |
| `DSSC-DEX-09` | must | [data-exchange](data-exchange.md) | The data payload specification must state how the data schema (from the Data Models build… |
| `DSSC-DEX-18` | must | [data-exchange](data-exchange.md) | When implementing the capability, a difference shall be made between a control plane and… |
| `DSSC-DEX-19` | must | [data-exchange](data-exchange.md) | The data plane and control plane shall work together, to ensure any access and usage poli… |
| `DSSC-DEX-20` | must | [data-exchange](data-exchange.md) | Exchanges between control planes of different parties shall use the Dataspace protocol as… |
| `DSSC-DEX-22` | must | [data-exchange](data-exchange.md) | The data plane needs to work closely together with the control plane of the Participant a… |
| `DSSC-DEX-25` | must | [data-exchange](data-exchange.md) | A data space must establish clear agreements on which data exchange protocols are used. |
| `DSSC-DEX-26` | must | [data-exchange](data-exchange.md) | The agreements about the data exchange protocols to be used must be documented in the dat… |
| `DSSC-DEX-31` | must | [data-exchange](data-exchange.md) | The protocol must be capable of carrying the payload as defined by the data schema from t… |
| `DSSC-DEX-32` | must | [data-exchange](data-exchange.md) | The protocol must operate within the rules established on the control plane, such as thos… |
| `DSSC-DEX-33` | must | [data-exchange](data-exchange.md) | The data space governance authority is responsible for maintaining a precise inventory of… |
| `DSSC-DEX-34` | must | [data-exchange](data-exchange.md) | The inventory of protocol specifications must be made available to all participants via t… |
| `DSSC-DEX-37` | must | [data-exchange](data-exchange.md) | The protocol must be able to maintain a consistent quality of service, for example, by ma… |
| `DSSC-DEX-39` | must | [data-exchange](data-exchange.md) | Once approved, the protocol description for the data exchange has to be published [in] th… |
| `DSSC-DEX-55` | must | [data-exchange](data-exchange.md) | The protocol must specify how requests are handled, functional and technical (synchronous… |
| `DSSC-DEX-56` | must | [data-exchange](data-exchange.md) | The specification must define a consistent use of status codes (when using HTTP) to commu… |
| `DSSC-DEX-57` | must | [data-exchange](data-exchange.md) | The protocol must specify how participants are authenticated, linking back to the identit… |
| `DSSC-DEX-58` | must | [data-exchange](data-exchange.md) | The protocol must specify what participants are authorized to do, linking back to the pol… |
| `DSSC-DEX-60` | must | [data-exchange](data-exchange.md) | A data exchange protocol requires a governance process to ensure its up to date. |
| `DSSC-DEX-61` | must | [data-exchange](data-exchange.md) | The governance process for a data exchange protocol must be documented in the rulebook. |
| `DSSC-DMO-01` | must | [data-models](data-models.md) | Data providers must describe their data structures, data formats, vocabularies, classific… |
| `DSSC-DMO-16` | must | [data-models](data-models.md) | A data model management process is required for maintaining the data models. |
| `DSSC-DMO-35` | must | [data-models](data-models.md) | Agreements on the use of existing models in the data space must be documented in the gove… |
| `DSSC-DMO-37` | must | [data-models](data-models.md) | A data space that creates its own model needs to set up a data model management process i… |
| `DSSC-DMO-38` | must | [data-models](data-models.md) | Setting up a data model management process involves setting guidelines for creating and m… |
| `DSSC-DMO-39` | must | [data-models](data-models.md) | Setting up a data model management process involves establishing processes for resolving… |
| `DSSC-DSO-10` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Participants in dataspaces need mechanisms for creating metadata for describing data prod… |
| `DSSC-DSO-16` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Every data provider shall provide, for each data product, functional metadata on the data… |
| `DSSC-DSO-17` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Every data provider shall provide, for each data product, the data structures, data forma… |
| `DSSC-DSO-18` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Every data provider shall provide, for each data product, the technical means to access t… |
| `DSSC-DSO-19` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Data space governance authorities need to address the co-creation question: what is the m… |
| `DSSC-DSO-21` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The outcomes of the co-creation question need to be documented in the rulebook of the dat… |
| `DSSC-DSO-36` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Both the data product provider and the data product consumer must adhere to specific prot… |
| `DSSC-IAM-04` | must | [participation](participation.md) | Every data space requires that issuance of verifiable credentials covering identity, memb… |
| `DSSC-IAM-05` | must | [participation](participation.md) | Every data space requires that validation of verifiable credentials covering identity, me… |
| `DSSC-IAM-26` | must | [participation](participation.md) | As part of the Federation services, the data space needs Trust services responsible for i… |
| `DSSC-IAM-27` | must | [participation](participation.md) | Trust services support delegation of trust/rights. |
| `DSSC-IAM-28` | must | [participation](participation.md) | Trust services interact with lifecycle management mechanisms. |
| `DSSC-IAM-30` | must | [participation](participation.md) | A common protocol for credential exchange — or compatible credential store implementation… |
| `DSSC-PTO-01` | must | [provenance-and-logging](provenance-and-logging.md) | A data space provides the capability of data provenance: backward looking in the data val… |
| `DSSC-PTO-02` | must | [provenance-and-logging](provenance-and-logging.md) | A data space provides the capability of transaction traceability: the ability to follow t… |
| `DSSC-PTO-05` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must answer for which data products provenance, traceability and observabi… |
| `DSSC-PTO-06` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must identify all relevant legislation (such as GDPR or the AI Act) that m… |
| `DSSC-PTO-07` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must identify typical contractual requirements (e.g. for billing or auditi… |
| `DSSC-PTO-08` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must determine which specific events on the Control Plane (observability)… |
| `DSSC-PTO-09` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must determine which events regarding the data transformation (provenance… |
| `DSSC-PTO-10` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must answer which data model will be used for recording and storing proven… |
| `DSSC-PTO-11` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must evaluate and choose an existing, open standard data model for structu… |
| `DSSC-PTO-12` | must | [provenance-and-logging](provenance-and-logging.md) | If the chosen standard is insufficient, the data space must define a domain-specific prof… |
| `DSSC-PTO-13` | must | [provenance-and-logging](provenance-and-logging.md) | Such a domain-specific profile must be documented. |
| `DSSC-PTO-14` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must answer how the logs will be stored securely and who can access them. |
| `DSSC-PTO-15` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must decide whether logs will be stored locally by either or both of the p… |
| `DSSC-PTO-16` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must define clear rules on who can access the logs, under what conditions,… |
| `DSSC-PTO-17` | must | [provenance-and-logging](provenance-and-logging.md) | These access and usage policies must be technically enforceable. |
| `DSSC-PTO-19` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must answer how the agreements on provenance, traceability and observabili… |
| `DSSC-PTO-20` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must record the mandatory events, the chosen data models, the storage arch… |
| `DSSC-PTO-21` | must | [provenance-and-logging](provenance-and-logging.md) | The data space must define a process for maintaining and updating these rules as part of… |
| `DSSC-PTO-58` | must | [provenance-and-logging](provenance-and-logging.md) | Information collected about observability, provenance, and traceability must be captured… |
| `DSSC-PTO-75` | must | [provenance-and-logging](provenance-and-logging.md) | It needs to be defined which entity stores which part of the P&T data, which might also i… |
| `DSSC-PTO-81` | must | [provenance-and-logging](provenance-and-logging.md) | The trust between a third party observer and all other parties must always be ensured for… |
| `DSSC-PTO-84` | must | [provenance-and-logging](provenance-and-logging.md) | An appropriate data model for each type of P&T data storage must be chosen that is capabl… |
| `DSSC-PUB-01` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | A participant must expose the offerings of a participant agent via a catalogue interface,… |
| `DSSC-PUB-02` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | A participant must manage offerings in accordance with their lifecycle: publish, update,… |
| `DSSC-PUB-06` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The data space governance authority needs to make a decision on the architectural option… |
| `DSSC-PUB-08` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Within DSP the DCAT-AP based specification is used as syntax to exchange the metadata of… |
| `DSSC-PUB-12` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Implementation requires the Participant Agent to publish entries. |
| `DSSC-PUB-15` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue must process the publication of the offering(s) and inform the data provide… |
| `DSSC-PUB-16` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | After publication, potential data consumers must be able to discover the offering. |
| `DSSC-PUB-20` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | A data provider updating an offering must be authorized to modify the offering in the cat… |
| `DSSC-PUB-21` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | An offering may only be updated if it has previously been published in the catalogue. |
| `DSSC-PUB-22` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue must process the update of the offering(s) and inform the data provider of… |
| `DSSC-PUB-24` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue must process the removal of the offering(s) and inform the data provider of… |
| `DSSC-PUB-28` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue must accept a request from a data consumer that includes the parameters to… |
| `DSSC-PUB-29` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue must compose a collection of relevant offerings based on the request. |
| `DSSC-PUB-30` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The catalogue must send the resulting collection of offerings to the data consumer. |
| `DSSC-PUB-31` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Where the data consumer is not authenticated and/or authorized, the catalogue must deny a… |
| `DSSC-PUB-34` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Access to the data or service itself would require subsequent onboarding of the external… |
| `DSSC-PUB-36` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | Offerings are deployed inside catalogues and represented using the `DCAT:Catalog` class a… |
| `DSSC-PUB-37` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | DCAT needs to be extended using DCAT-AP for the use in a specific data space. |
| `DSSC-PUB-39` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | In the context of the Dataspace Protocol, a catalogue is a collection of offerings publis… |
| `DSSC-PUB-42` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | A catalogue request returns the catalogue's content with references to all its entries. |
| `DSSC-PUB-44` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | A dataset request returns a specific entry of the catalogue. |
| `DSSC-SVD-34` | must | [data-exchange](data-exchange.md) | The Participant agent shall use the Dataspace Protocol for the exchange of catalogue entr… |
| `DSSC-SVD-35` | must | [catalogue-and-metadata](catalogue-and-metadata.md) | The Participant agent shall use DCAT-AP, in combination with the Dataspace Protocol, for… |
| `DSSC-SVD-38` | must | [policies](policies.md) | After publishing, a contract negotiation process needs to occur, during which the policie… |
| `DSSC-SVD-41` | must | [data-exchange](data-exchange.md) | The Participant agents shall use the Dataspace Protocol for the contract negotiation proc… |
| `DSSC-TRF-01` | must | [participation](participation.md) | A data space requires a Rulebook that defines governance requirements. |
| `DSSC-TRF-03` | must | [participation](participation.md) | A data space requires compliance verification processes and services that operationalise… |
| `DSSC-TRF-08` | must | [participation](participation.md) | For each of the credentials identified in the Identity and Attestation management buildin… |
| `DSSC-TRF-12` | must | [participation](participation.md) | Processes and technical means for validation require defining the format of claims. |
| `DSSC-TRF-13` | must | [participation](participation.md) | Processes and technical means for validation require establishing mechanisms to collect c… |
| `DSSC-TRF-14` | must | [participation](participation.md) | Processes and technical means for validation require making the criteria machine-readable. |
| `DSSC-XCT-02` | must | [personal-data](personal-data.md) | Pseudonymised data, and personal data without PII, must be considered as personal data. |
| `DSSC-XCT-04` | must | [personal-data](personal-data.md) | B2B data sharing that includes personal data requires that there are legitimate grounds f… |
| `DSSC-XCT-05` | must | [personal-data](personal-data.md) | B2B data sharing that includes personal data requires that purpose limitation is applied. |
| `DSSC-XCT-06` | must | [personal-data](personal-data.md) | Where consent is the legal basis, the data space needs to accommodate a cross-organisatio… |
| `DSSC-XCT-08` | must | [personal-data](personal-data.md) | Sharing personal data on legitimate grounds other than consent requires appropriate data… |
| `DSSC-XCT-09` | must | [personal-data](personal-data.md) | In scenarios where personal data is shared, the identity management capability must be ab… |
| `DSSC-XCT-17` | must | [personal-data](personal-data.md) | Designing intermediary roles for the data space must acknowledge that certain types of in… |
| `DSSC-XCT-26` | must | [personal-data](personal-data.md) | C2I2B sharing of personal data: the intermediary must have means to manage consent or oth… |

### Binding rows accepted and not met

| Requirement | Force | What is missing |
|---|---|---|
| `DSSC-AUP-06` | must | Only the policy validity window is missing: `valid_from` / `valid_until` are declared in governance and reported by the `declared-not-enforced` check, and never emitted as an ODRL constraint (`A-9`). Closing it needs a date operand bound in the EDC, not a mapper change |
| `DSSC-AUP-45` | must | The conflict-resolution and validation gate runs, but not over everything it claims: the two participant checks need a live identity-registry and so run outside CI, and CI validates one producer's governance rather than every producer's (`A-4`) |
| `DSSC-AUP-46` | must | Same gap as `DSSC-AUP-45`: the required/optional distinction is checked, and the checking is not complete — the participant checks need a live registry and CI covers one producer's governance (`A-4`) |
| `DSSC-DEX-38` | must | Each ds service publishes its own OpenAPI document (`X-13`), and **the DSP surface publishes no machine-readable capability description** — the protocol version, bindings and endpoints a counterparty would read before interacting. Serving one is a capability decision rather than a defect fix |
| `DSSC-DMO-17` | must | No collaboration with a standards development organisation exists, and none can be code: this is an obligation on a deployment's governance authority, which the platform can neither discharge nor evidence |
| `DSSC-DMO-19` | must | Publishing, browsing and maintaining are served (§4); three functions are not. Editing through the surface is deliberately a commit and a sync (§5.1 applied consistently, `M-11`), and the two genuinely absent ones are **documenting non-standardised data at ingestion** and **version history** — the registry carries one `version` per entry, not a record of how a vocabulary changed |
| `DSSC-DSO-12` | must | `C-13` reads *Not enforced*: there is no machine-readable projection of this rulebook for a check to consult. One existed and was removed the same day as the rule-id citations, because the record it checked against was 79% unevidenced assertion. Closing it honestly needs the rulebook's statuses backed by evidence that runs — the same prerequisite as Participation §5 |
| `DSSC-DSO-14` | must | Metadata versioning is not implemented. `governance.yaml` is versioned in git, which is version control of the *file*, not of an offering's metadata across the data product's lifetime — a consumer cannot ask what a description said when they negotiated. §5 puts it second and notes it needs a design decision first: version the offering, or snapshot it into the agreement |
| `DSSC-DSO-15` | must | Same gap as `DSSC-DSO-14`, and the same blocked design decision: there is no metadata version history at all, only git history of the file that declares it |
| `DSSC-PTO-03` | must | Observability: **not a scope decision — an unfilled gap**, and a narrowing one. Traces now span the services and the DSP hop, correlated by `ds.dsp.agreement_id`, and all five services serve `/metrics` (§5, steps 1-3). Step 4 is what is left: no collection or visualisation, no real-time monitoring, and SLIs derivable but not built. Listed here so it is not mistaken for a declared exclusion |
| `DSSC-PTO-42` | must | Nothing states, let alone satisfies, horizontal (cross-sector) observability requirements — §5 records this pair as flatly absent, and the requirements themselves have not been written down for this platform |
| `DSSC-PTO-43` | must | Same as `DSSC-PTO-42` for vertical (energy-sector) requirements: absent, and not yet stated |
| `DSSC-PTO-44` | must | Security controls **for the observability data itself**: `/metrics` exposure is answered by the chart (default-deny, Prometheus namespace only) and nothing else is. There is no access control or retention rule for traces, and no collector to apply one in |
| `DSSC-PTO-45` | must | Audit trail: partial. The compliance access log is materialised from `QueryExecuted` (`L-12`), which covers data access; the *observability* plane has no audit trail — who read a trace or a metric series is unrecorded |
| `DSSC-PTO-46` | must | No compliance documentation is produced for observability. `task compliance:evidence` emits DCAT-AP and ODRL evidence for governance, and there is no equivalent artifact describing what is monitored, retained or reported |
| `DSSC-PTO-57` | informative | The row is the blueprint saying its event table is a starting point rather than a closed set. What is missing here is the *decision*: this rulebook fixes sixteen event types (`L-1`) and nowhere records which of the blueprint's remaining suggestions were considered and declined, so a reader cannot tell a deliberate omission from an oversight. Informative, so nothing demands it |
| `DSSC-PTO-60` | should | Reuse of existing standards is done where data is stored (PROV-O) and **undecided where it is not**: the observability plane has no chosen standard because it has no model at all. The row cannot close while `DSSC-PTO-42`-`-46` are open |
| `DSSC-PTO-61` | should | Extend-or-create is the same decision as `DSSC-PTO-60`, unmade for the same reason: nothing has reached the point of choosing between reusing an observability model and defining one |
| `DSSC-PTO-62` | informative | The blueprint's own statement that no single semantic standard fits. What is missing is this rulebook's answer to it for telemetry — for provenance the answer is PROV-O and is recorded. Informative, so nothing demands it |
| `DSSC-PTO-63` | recommended | PROV-O **is** adopted, for provenance and traceability, and is the whole of the provenance service's model. PAV is not used, and the observability half aligns with no standard yet. The row stays open for that remainder rather than for the recommendation it names. Recommended, so nothing demands it |
| `DSSC-PTO-83` | must | Declared and **unmeasured**: no load test, no latency budget and no measurement of what the provenance write and the per-query authorize call cost the exchange. Nothing suggests a problem; nothing rules one out either, which is the gap |
| `DSSC-PUB-03` | must | Visibility is enforced at **negotiation, not at discovery** (`C-21`, *Partly enforced* and accepted as such on 2026-08-09): a participant outside an offering's audience can still see that the offering exists, and is refused when it tries to contract. What is missing is audience filtering in the catalogue response itself |
| `DSSC-PUB-45` | must | A catalogue response **embeds** each entry's metadata rather than returning `dcat:record` identifiers for a consumer to dereference. `C-8` emits a `dcat:CatalogRecord` per entry, so the records exist; what is missing is the by-reference response shape this row asks for |

### Binding rows deliberately declined

Each belongs in [Scope and deviations](scope-and-deviations.md) as well; this table is the index, that page is the argument.

| Requirement | Force | Reason |
|---|---|---|
| `CEEDS-ARC-08` | informative | A marketplace or clearing house: Out of scope — follows from §1 |
| `CEEDS-CON-31` | informative | HEMRM role model: Not adopted. The platform's role model is a platform role model; a deployment needing HEMRM must map onto it |
| `CEEDS-INT-11` | informative | A marketplace or clearing house: Out of scope — follows from §1 |
| `CEEDS-INT-27` | recommended | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `CEEDS-INT-34` | recommended | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `CEEDS-INT-36` | must | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `CEEDS-INT-42` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `CEEDS-INT-43` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `CEEDS-INT-49` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `CEEDS-STD-04` | informative | HEMRM role model: Not adopted. The platform's role model is a platform role model; a deployment needing HEMRM must map onto it |
| `CEEDS-STD-07` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `CEEDS-STD-11` | informative | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `CEEDS-STD-12` | informative | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `CEEDS-STD-23` | must | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `CEEDS-STD-25` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `CEEDS-STD-26` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `CEEDS-STD-28` | informative | SGAM, and the proposed 6th layer: Not referenced. These are architectural framing rather than implementable obligations |
| `DSSC-DEX-06` | must | Push and streaming transfers: Out of scope. HTTP pull, finite datasets, one agreement per transfer |
| `DSSC-DEX-07` | must | Push and streaming transfers: Out of scope. HTTP pull, finite datasets, one agreement per transfer |
| `DSSC-DEX-50` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-DEX-51` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-DEX-52` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-DEX-64` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-DEX-65` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-DMO-08` | may | Standardised discovery of data models *across data spaces*: not applicable while federation is out of scope — follows §1, the same exclusion that carries `DSSC-DEX-50`-`-52`. Also a `may` row |
| `DSSC-DMO-27` | must | Payload semantic models: Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| `DSSC-DSO-41` | must | DCAT-AP-HVD binds only datasets the EU designates as high-value. Not applicable until a deployment designates one, and then it is that deployment's stricter metadata obligation — the same 'deferred to the deployment, not to nobody' pattern as the payload semantic models in §2 |
| `DSSC-VCS-01` | may | no value creation services (§1) |
| `DSSC-VCS-04` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-05` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-06` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-07` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-09` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-10` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-12` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-13` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-14` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-15` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-19` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-20` | should | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-22` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-23` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-24` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-25` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-26` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-27` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-28` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-29` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-30` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-31` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-32` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-33` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-34` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-35` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-36` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-37` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-38` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-41` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-43` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-44` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-45` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-46` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-47` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-48` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-49` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-50` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-51` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-52` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-53` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-54` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-56` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-57` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-58` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-59` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-60` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-61` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-62` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-63` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-64` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-65` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-66` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-67` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-68` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-70` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-73` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-VCS-75` | must | no value creation services (scope-and-deviations.md §1). DSSC-VCS-01 states the capability is not mandatory; the remaining rows are conditional on including such services and none applies |
| `DSSC-XCT-27` | must | Anonymisation capability: Out of scope. A deployment needing intermediated sharing of anonymised data must anonymise before ingest; this platform cannot prove effective anonymisation |
| `DSSC-XCT-30` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-XCT-31` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-XCT-41` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| `DSSC-XCT-43` | must | Cross-data-space federation: Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |

## Structural problems

None.

## Moving a row

**To evidence a rule**, put the marker on the test that already checks it:

```python
@pytest.mark.rule("A-11")
def test_sustained_silence_denies() -> None: ...
```

```java
@Test @Tag("rule:A-11")
void sustainedSilenceDenies() { … }
```

```python
class ConsentWithdrawalFlow(Flow):     # libs/ds-e2e/src/ds_e2e/flows/
    rules = ("D-17", "CR-5")
```

```ts
test('a viewer cannot write @rule:P-12', async ({ page }) => { … })
```

**If no such test exists**, that is the finding — write the check, or change the row to say what is true. The honesty rule allows exactly four markers and `Declared` is an honourable one.

**To disposition a blueprint row**, add it to `docs/rulebook/coverage.yaml`:

```yaml
dispositions:
  DSSC-AUP-01:
    state: covered            # covered | open | out-of-scope | unassessed
    rules: [A-3, A-4]
  DSSC-AUP-06:
    state: open
    note: the validity window needs a date operand bound in the EDC first
```


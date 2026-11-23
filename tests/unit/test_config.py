from config import AWS_REGION, MARKETPLACES, MODEL_ID_AGENT, MODEL_ID_TOOLS, PRICING


class TestMarketplaceMapping:
    def test_all_marketplaces_have_domains(self):
        for code, domain in MARKETPLACES.items():
            assert isinstance(code, str)
            assert isinstance(domain, str)
            assert domain.startswith("www.amazon") or domain.startswith("amazon")

    def test_major_marketplaces_present(self):
        assert "US" in MARKETPLACES
        assert "UK" in MARKETPLACES
        assert "DE" in MARKETPLACES
        assert "JP" in MARKETPLACES

    def test_us_marketplace_maps_to_com(self):
        assert MARKETPLACES["US"] == "www.amazon.com"

    def test_uk_marketplace_maps_to_co_uk(self):
        assert MARKETPLACES["UK"] == "www.amazon.co.uk"

    def test_marketplace_codes_are_uppercase(self):
        for code in MARKETPLACES.keys():
            assert code.isupper()

    def test_no_duplicate_domains(self):
        domains = list(MARKETPLACES.values())
        assert len(domains) == len(set(domains))

    def test_marketplace_count_matches_documented_total(self):
        assert len(MARKETPLACES) == 25


class TestAWSConfiguration:
    def test_aws_region_is_string(self):
        assert isinstance(AWS_REGION, str)
        assert len(AWS_REGION) > 0

    def test_model_id_tools_is_nova_micro(self):
        assert "nova-micro" in MODEL_ID_TOOLS.lower()

    def test_model_id_agent_is_haiku(self):
        assert "haiku" in MODEL_ID_AGENT.lower()

    def test_model_ids_are_bedrock_format(self):
        assert "." in MODEL_ID_TOOLS
        assert "." in MODEL_ID_AGENT


class TestPricingConfiguration:
    def test_pricing_includes_both_models(self):
        assert MODEL_ID_TOOLS in PRICING
        assert MODEL_ID_AGENT in PRICING

    def test_each_model_has_input_and_output_pricing(self):
        for model_id, prices in PRICING.items():
            assert "input" in prices
            assert "output" in prices

    def test_pricing_values_are_positive(self):
        for model_id, prices in PRICING.items():
            assert prices["input"] > 0
            assert prices["output"] > 0

    def test_nova_micro_is_cheaper_than_haiku(self):
        nova_input = PRICING[MODEL_ID_TOOLS]["input"]
        haiku_input = PRICING[MODEL_ID_AGENT]["input"]
        assert nova_input < haiku_input

    def test_output_costs_more_than_input(self):
        for model_id, prices in PRICING.items():
            assert prices["output"] > prices["input"]


class TestMarketplaceRegions:
    def test_americas_marketplaces(self):
        americas = ["US", "CA", "MX", "BR", "CO"]
        for code in americas:
            assert code in MARKETPLACES

    def test_europe_marketplaces(self):
        europe = ["UK", "DE", "FR", "IT", "ES", "NL", "SE", "PL", "BE", "IE", "TR"]
        for code in europe:
            assert code in MARKETPLACES

    def test_asia_pacific_marketplaces(self):
        apac = ["IN", "JP", "SG", "AU"]
        for code in apac:
            assert code in MARKETPLACES

    def test_middle_east_africa_marketplaces(self):
        mea = ["AE", "SA", "EG", "ZA", "NG"]
        for code in mea:
            assert code in MARKETPLACES


class TestDomainFormatting:
    def test_all_domains_contain_amazon(self):
        for domain in MARKETPLACES.values():
            assert "amazon" in domain.lower()

    def test_no_domains_have_trailing_slashes(self):
        for domain in MARKETPLACES.values():
            assert not domain.endswith("/")

    def test_no_domains_have_protocols(self):
        for domain in MARKETPLACES.values():
            assert not domain.startswith("http://")
            assert not domain.startswith("https://")

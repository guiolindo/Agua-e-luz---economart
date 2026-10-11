"""Avisos de plausibilidade na conferência (achado da bateria com o Gemini real: foto ruim gera números errados com confiança alta)."""
from app.schemas.extraction import BillExtraction
from app.services.import_service import plausibility_warnings


def _e(**kw):
    return BillExtraction(is_energy_bill=True, **kw)


def test_normal_bill_has_no_warning():
    assert plausibility_warnings(_e(total_value=18345.67, consumption_hp_kwh=4210, consumption_hfp_kwh=61870,
                                    demand_hfp_kw=142, contracted_demand_kw=150)) == []


def test_absurd_price_per_kwh_warns():
    """Foto escura: o total saiu certo e o consumo saiu 4,2 + 45,8 kWh em vez de 4.210 + 61.870."""
    w = plausibility_warnings(_e(total_value=18345.67, consumption_hp_kwh=4.2, consumption_hfp_kwh=45.8))
    assert len(w) == 1 and "kWh" in w[0] and "R$ 366" in w[0]


def test_demand_far_from_contracted_warns():
    w = plausibility_warnings(_e(total_value=1000, consumption_kwh=2000, demand_hp_kw=500, contracted_demand_kw=150))
    assert any("contratada" in x for x in w)


def test_missing_data_never_warns():
    assert plausibility_warnings(_e(total_value=500.0)) == []
    assert plausibility_warnings(_e(consumption_kwh=300)) == []


def test_invalid_api_key_is_not_reported_as_a_bad_file():
    """Bateria com o Gemini real: chave inválida volta como HTTP 400 e a tela dizia "arquivo inválido"."""
    from app.services.gemini_service import _is_bad_key, message_for_code

    assert _is_bad_key(Exception("400 INVALID_ARGUMENT. {'error': {'message': 'API key not valid. Please pass a valid API key.'}}"))
    assert not _is_bad_key(Exception("400 INVALID_ARGUMENT: request payload size exceeds the limit"))
    assert "chave" in message_for_code(401).lower()

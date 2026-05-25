from src.models import Bill, Parameters, TenantBlacklistEntry, TenantSettlement, ApartmentSettlement, Transfer
from src.manager import Manager


def test_settlement_due_between_tanants_and_apartment():
    manager = Manager(Parameters())

    settlement: ApartmentSettlement = manager.get_settlement('apart-polanka', 2025, 1)
    
    tenants_settlements: list[TenantSettlement] = manager.create_tenants_settlements(settlement)
    assert len(tenants_settlements) == 3

    total_due = sum([tenant_settlement.total_due_pln for tenant_settlement in tenants_settlements])
    assert total_due == settlement.total_due_pln

def test_debtors_calculation():
    manager = Manager(Parameters())

    debtors = manager.get_debtors('apart-polanka', 2025, 1)
    assert len(debtors) == 0

    debtors = manager.get_debtors('apart-polanka', 2025, 2)
    assert len(debtors) == 3


def test_tax_calculation():
    manager = Manager(Parameters())
    
    tax = manager.calculate_tax(2025, 1, 0.085)
    assert tax == 638 # 0.085 * 7500.0

    tax = manager.calculate_tax(2025, 2, 0.085)
    assert tax == 0

def test_deposits_calculation():
    manager = Manager(Parameters())
    
    deposit_balance = manager.check_deposits()
    assert deposit_balance == -8700.0 # no deposit in transfers

    manager.transfers.append(Transfer(
        tenant='tenant-1',
        date='2025-01-01',
        settlement_year=None,
        settlement_month=None,
        amount_pln=1000.0,
        type='deposit'
    ))

    deposit_balance = manager.check_deposits()
    assert deposit_balance == -7700.0 # 1000.0 deposit in transfers

def test_annual_balance_calculation():
    manager = Manager(Parameters())
    
    annual_balance = manager.get_annual_balance(2025)
    assert annual_balance == 6490.0 # 7500.0 in transfers minus 910.0 in bills

    manager.bills.append(Bill(
        apartment='apart-polanka',
        date_due='2025-02-15',
        settlement_year=2025,
        settlement_month=5,
        amount_pln=500.0,
        type='rent'
    ))

    manager.bills.append(Bill(
        apartment='apart-polanka',
        date_due='2025-02-15',
        settlement_year=2025,
        settlement_month=5,
        amount_pln=4500.0,
        type='renovation'
    ))

    annual_balance = manager.get_annual_balance(2025)
    assert annual_balance == 1490.0 # 7500.0 in transfers minus 910.0 in bills minus new bills 500.0 and 4500.0

def test_apartment_has_any_bills():
    manager = Manager(Parameters())
    
    has_bills = manager.has_any_bills('apart-polanka', 2025, 1)
    assert has_bills == True

    has_bills = manager.has_any_bills('apart-polanka', 2025, 3)
    assert has_bills == False

def test_min_max_transfer_amount():
    manager = Manager(Parameters())

    success = manager.check_transfers_amount_range()
    assert success == True

    manager.transfers[-1].amount_pln = 10000
    success = manager.check_transfers_amount_range()
    assert success == False

    manager.transfers[-1].amount_pln = -3000
    success = manager.check_transfers_amount_range()
    assert success == False

def test_tenant_blacklist_check():
    manager = Manager(Parameters())

    is_blacklisted = manager.check_tenant_blacklist('Jan Pawlak')
    assert is_blacklisted == False

    manager.tenants_blacklist.append(TenantBlacklistEntry(
        tenant='Jan Pawlak',
        reason='Previous unpaid rent'
    ))

    is_blacklisted = manager.check_tenant_blacklist('Jan Pawlak')
    assert is_blacklisted == True

def test_transfer_valid_with_tenant_agreement():
    manager = Manager(Parameters())

    is_valid = manager.check_transfers_tenant()
    assert is_valid == True

    manager.transfers.append(Transfer(
        tenant='non-existing-tenant',
        date='2025-01-01',
        settlement_year=2025,
        settlement_month=1,
        amount_pln=1000.0,
        type='rent'
    ))

    is_valid = manager.check_transfers_tenant()
    assert is_valid == False

    manager.transfers.pop()
    manager.transfers.append(Transfer(
        tenant='tenant-1',
        date='2025-01-01',
        settlement_year=1999,
        settlement_month=1,
        amount_pln=1000.0,
        type='rent'
    ))

    is_valid = manager.check_transfers_tenant()
    assert is_valid == False

def test_generate_apartment_events_report_coverage():
    import pytest
    from src.manager import Manager
    from src.models import Parameters, Apartment, ApartmentEvent
    
    manager = Manager(Parameters())
    
    manager.apartments = {
        'A1': Apartment(key='A1', name='Test', location='Test', area_m2=50.0, rooms={})
    }
    
    manager.apartment_events = [
        ApartmentEvent(date='2026-05-01', apartment='A1', description='Kran cieknie', solved=False),
        ApartmentEvent(date='2026-05-02', apartment='A1', description='Zarowka', solved=True),
        ApartmentEvent(date='2026-05-03', apartment='A2', description='Zle mieszkanie', solved=False)
    ]
    
    with pytest.raises(ValueError, match="Apartment key does not exist"):
        manager.generate_apartment_events_report('NIEZNANE_MIESZKANIE')
        
    unsolved_events = manager.generate_apartment_events_report('A1', only_unsolved=True)
    assert len(unsolved_events) == 1
    assert unsolved_events[0].description == 'Kran cieknie'
    
    all_events = manager.generate_apartment_events_report('A1', only_unsolved=False)
    assert len(all_events) == 2

def test_get_settlement_edge_cases_coverage():
    import pytest
    from unittest.mock import patch
    from src.manager import Manager
    from src.models import Parameters, Apartment
    
    manager = Manager(Parameters())
    
    manager.apartments = {
        'A1': Apartment(key='A1', name='Test', location='Test', area_m2=50.0, rooms={})
    }
    
    with pytest.raises(ValueError, match="Month must be between 1 and 12"):
        manager.get_settlement('A1', 2026, 13)
        
    assert manager.get_settlement('ZLE_MIESZKANIE', 2026, 5) is None
    
    with patch.object(manager, 'get_apartment_costs', return_value=None):
        assert manager.get_settlement('A1', 2026, 5) is None 


def test_has_any_bills_edge_cases_coverage():
    import pytest
    from src.manager import Manager
    from src.models import Parameters, Apartment
    
    manager = Manager(Parameters())
    
    manager.apartments = {
        'A1': Apartment(key='A1', name='Test', location='Test', area_m2=50.0, rooms={})
    }
    
    with pytest.raises(ValueError, match="Month must be between 1 and 12"):
        manager.has_any_bills('A1', 2026, 0) # 0 to zły miesiąc
        
    with pytest.raises(ValueError, match="Apartment key does not exist"):
        manager.has_any_bills('BRAK_TAKIEGO_KLUCZA', 2026, 5)   


def test_create_tenants_settlements_coverage():
    import pytest
    from src.manager import Manager
    from src.models import Parameters, Apartment, ApartmentSettlement, Tenant
    
    manager = Manager(Parameters())
    
    manager.apartments = {
        'A1': Apartment(key='A1', name='Test', location='Test', area_m2=50.0, rooms={})
    }
    
    bad_settlement = ApartmentSettlement(key='k', apartment='A1', month=13, year=2026, total_due_pln=0.0)
    with pytest.raises(ValueError, match="Month must be between 1 and 12"):
        manager.create_tenants_settlements(bad_settlement)
        
    unknown_settlement = ApartmentSettlement(key='k', apartment='A99', month=5, year=2026, total_due_pln=0.0)
    assert manager.create_tenants_settlements(unknown_settlement) is None
    
    empty_apartment_settlement = ApartmentSettlement(key='k', apartment='A1', month=5, year=2026, total_due_pln=0.0)
    assert manager.create_tenants_settlements(empty_apartment_settlement) == []
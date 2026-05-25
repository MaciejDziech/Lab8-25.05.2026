"""
Modul zarzadzajacy glowna logika biznesowa dla systemu wynajmu mieszkan.
"""
from datetime import datetime
from typing import List

from src.models import (
    Apartment, Bill, Parameters, Tenant, ApartmentEvent,
    TenantBlacklistEntry, TenantSettlement, Transfer, ApartmentSettlement
)


class Manager:
    """Glowna klasa menedzera do przetwarzania danych."""

    def __init__(self, parameters: Parameters):
        """Inicjalizacja menedzera z przekazanymi parametrami."""
        self.parameters = parameters

        self.apartments = {}
        self.tenants = {}
        self.transfers = []
        self.bills = []
        self.tenants_blacklist = []
        self.apartment_events = []
        self.load_data()

    def load_data(self):
        """Wczytywanie danych bazowych z plikow JSON."""
        self.apartments = Apartment.from_json_file(self.parameters.apartments_json_path)
        self.tenants = Tenant.from_json_file(self.parameters.tenants_json_path)
        self.transfers = Transfer.from_json_file(self.parameters.transfers_json_path)
        self.bills = Bill.from_json_file(self.parameters.bills_json_path)
        self.tenants_blacklist = TenantBlacklistEntry.from_json_file(
            self.parameters.tenants_blacklist_json_path
        )

    def load_additional_data(self):
        """Wczytywanie dodatkowych danych JSON, takich jak usterki."""
        self.apartment_events = ApartmentEvent.from_json_file(
            self.parameters.apartment_events_json_path
        )

    def generate_apartment_events_report(
        self, apartment_key: str, only_unsolved: bool = True
    ) -> List[ApartmentEvent]:
        """Generowanie raportu usterek dla danego mieszkania."""
        if apartment_key not in self.apartments:
            raise ValueError("Apartment key does not exist")
        return [
            event for event in self.apartment_events
            if event.apartment == apartment_key and (not event.solved or not only_unsolved)
        ]

    def check_tenants_apartment_keys(self) -> bool:
        """Weryfikacja, czy wszyscy najemcy naleza do istniejacych mieszkan."""
        for tenant in self.tenants.values():
            if tenant.apartment not in self.apartments:
                return False
        return True

    def get_apartment(self, apartment_key: str) -> Apartment | None:
        """Pobieranie obiektu mieszkania na podstawie jego klucza."""
        return self.apartments.get(apartment_key, None)

    def get_apartment_costs(
        self, apartment_key: str, year: int = None, month: int = None
    ) -> float | None:
        """Obliczanie calkowitych rachunkow dla konkretnego mieszkania i daty."""
        if month is not None and (month < 1 or month > 12):
            raise ValueError("Month must be between 1 and 12")
        if apartment_key not in self.apartments:
            return None
        total_cost = 0.0
        for bill in self.bills:
            if (bill.apartment == apartment_key and
                    (year is None or bill.settlement_year == year) and
                    (month is None or bill.settlement_month == month)):
                total_cost += bill.amount_pln
        return total_cost

    def get_settlement(
        self, apartment_key: str, year: int, month: int
    ) -> ApartmentSettlement | None:
        """Pobieranie szczegolow miesiecznego rozliczenia dla mieszkania."""
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        if apartment_key not in self.apartments:
            return None
        total_cost = self.get_apartment_costs(apartment_key, year, month)
        if total_cost is None:
            return None

        return ApartmentSettlement(
            key=f"{apartment_key}-{year}-{month}",
            apartment=apartment_key,
            year=year,
            month=month,
            total_due_pln=total_cost
        )

    def create_tenants_settlements(
        self, apartment_settlement: ApartmentSettlement
    ) -> List[TenantSettlement] | None:
        """Rowny podzial kosztow mieszkania miedzy przypisanych do niego najemcow."""
        if apartment_settlement.month < 1 or apartment_settlement.month > 12:
            raise ValueError("Month must be between 1 and 12")
        if apartment_settlement.apartment not in self.apartments:
            return None

        tenants_in_apartment = [
            t for t in self.tenants.values() if t.apartment == apartment_settlement.apartment
        ]
        if not tenants_in_apartment:
            return []

        cost_per_tenant = apartment_settlement.total_due_pln / len(tenants_in_apartment)
        return [
            TenantSettlement(
                tenant=tenant.name,
                apartment_settlement=apartment_settlement.key,
                month=apartment_settlement.month,
                year=apartment_settlement.year,
                total_due_pln=cost_per_tenant
            )
            for tenant in tenants_in_apartment
        ]

    def get_debtors(self, apartment_key: str, year: int, month: int) -> List[str]:
        """Wyszukiwanie najemcow, ktorzy nie zaplacili wystarczajaco duzo."""
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        output = []
        settlement = self.get_settlement(apartment_key, year, month)
        
        # Zabezpieczenie przed pustym rozliczeniem
        if not settlement:
            return output
            
        tenant_settlements = self.create_tenants_settlements(settlement)

        for ts in tenant_settlements:
            tenant_transfers = [
                t for t in self.transfers
                if self.tenants[t.tenant].name == ts.tenant
                and t.settlement_year == year and t.settlement_month == month
            ]
            total_paid = sum(t.amount_pln for t in tenant_transfers)
            if total_paid < ts.total_due_pln:
                output.append(ts.tenant)
        return output

    def calculate_tax(self, year: int, month: int, tax_rate: float) -> float:
        """Obliczanie podatku od przychodow z wynajmu."""
        total_income = sum(
            t.amount_pln for t in self.transfers
            if t.settlement_year == year and t.settlement_month == month
        )
        return round(total_income * tax_rate, 0)

    def check_deposits(self) -> float:
        """Sprawdzanie stanu wplaconych kaucji najemcow."""
        total_deposits = 0.0
        total_due = 0.0
        for tenant in self.tenants.values():
            total_deposits += sum(
                t.amount_pln for t in self.transfers
                if self.tenants[t.tenant].name == tenant.name and t.type == 'deposit'
            )
            total_due += tenant.deposit_pln
        return total_deposits - total_due

    def get_annual_balance(self, year: int) -> float:
        """Obliczanie rocznego bilansu finansowego (przychody minus koszty)."""
        total_income = sum(
            t.amount_pln for t in self.transfers if t.settlement_year == year
        )
        total_due = sum(
            b.amount_pln for b in self.bills if b.settlement_year == year
        )
        return total_income - total_due

    def has_any_bills(self, apartment_key: str, year: int, month: int) -> bool:
        """Sprawdzanie, czy w danym miesiacu i roku wystepuja jakikolwiek rachunki."""
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        if apartment_key not in self.apartments:
            raise ValueError("Apartment key does not exist")
        return any(
            b for b in self.bills
            if b.apartment == apartment_key and
            b.settlement_year == year and b.settlement_month == month
        )

    def check_transfers_amount_range(self) -> bool:
        """Sprawdzanie, czy wszystkie przelewy mieszcza sie w dopuszczalnych zakresach kwot."""
        for transfer in self.transfers:
            if (transfer.amount_pln > self.parameters.max_transfer_pln or
                    transfer.amount_pln < -self.parameters.max_refund_pln):
                return False
        return True

    def check_tenant_blacklist(self, tenant_name: str) -> bool:
        """Sprawdzanie, czy dany najemca znajduje sie na czarnej liscie."""
        return any(entry for entry in self.tenants_blacklist if entry.tenant == tenant_name)

    def check_transfers_tenant(self) -> bool:
        """Weryfikacja przelewow pod katem poprawnosci najemcow i dat ich umow."""
        for transfer in self.transfers:
            if transfer.tenant not in self.tenants:
                return False
            if transfer.settlement_year is not None and transfer.settlement_month is not None:
                tenant = self.tenants[transfer.tenant]
                a_from = datetime.strptime(tenant.date_agreement_from, "%Y-%m-%d").date()
                a_to = datetime.strptime(tenant.date_agreement_to, "%Y-%m-%d").date()
                if (transfer.settlement_year < a_from.year or
                        transfer.settlement_year > a_to.year):
                    return False
        return True
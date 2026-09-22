import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import type {
  CustomerSummaryQuery,
  CustomerSummaryResponse,
  OvLinksResponse,
  PortalServiceItem,
} from "../types";

/** Home/Account: snapshot default, sin connectivity probe. */
const HOME_QUERY: CustomerSummaryQuery = {
  // Default backend ya omite connectivity; explicitamos para claridad.
  connectivity: "omit",
};

export function useCustomerSummary({
  token,
  onAuthExpired,
  query = HOME_QUERY,
}: {
  token: string;
  onAuthExpired: () => void;
  query?: CustomerSummaryQuery;
}) {
  const [data, setData] = useState<CustomerSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!token || inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError("");
    try {
      const res = await api.getCustomerSummary(token, query);
      if (!mounted.current) return;
      setData(res);
    } catch (err) {
      if (!mounted.current) return;
      if (isAuthExpired(err)) {
        onAuthExpired();
        return;
      }
      setError(
        formatUserError(
          err,
          "No pudimos cargar el resumen de tu cuenta. Intentá nuevamente.",
        ),
      );
      setData(null);
    } finally {
      inFlight.current = false;
      if (mounted.current) setLoading(false);
    }
    // query fields: evitar re-fetch por identidad de objeto.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- serializamos query
  }, [
    token,
    onAuthExpired,
    query?.include,
    query?.refresh,
    query?.connectivity,
    query?.service_id,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(() => {
    void load();
  }, [load]);

  const servicesDomain = data?.services;
  const serviceItems: PortalServiceItem[] =
    servicesDomain?.data?.items && Array.isArray(servicesDomain.data.items)
      ? servicesDomain.data.items
      : [];
  const servicesUnavailable = servicesDomain?.status === "unavailable";

  const billingDomain = data?.billing;
  const balanceAmount =
    billingDomain?.data?.balance &&
    typeof billingDomain.data.balance.amount === "string"
      ? billingDomain.data.balance.amount
      : null;
  const ovLinks: OvLinksResponse | null =
    billingDomain?.data?.ov && typeof billingDomain.data.ov === "object"
      ? billingDomain.data.ov
      : null;

  const accountData = data?.account?.data ?? null;
  // account.status (dominio) ≠ account.data.status (comercial)
  const accountDomainStatus = data?.account?.status ?? null;
  const accountCommercialStatus = accountData?.status ?? null;

  return {
    data,
    loading,
    error,
    refresh,
    // Services (compat con ServicesSection)
    serviceItems,
    servicesUnavailable,
    // Billing / OV
    balanceAmount,
    billingDomainStatus: billingDomain?.status ?? null,
    ovLinks,
    // Account commercial fields
    accountData,
    accountDomainStatus,
    accountCommercialStatus,
    plan: accountData?.plan ?? null,
  };
}

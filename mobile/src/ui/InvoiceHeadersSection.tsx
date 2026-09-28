import { ActivityIndicator, StyleSheet, View } from "react-native";

import { formatInvoiceIssuedAt, invoiceUiPhase } from "../invoicesView";
import { formatMontoDisplay, present } from "../present";
import { colors, spacing } from "../theme";
import type { PortalInvoiceHeader, PortalInvoicesResponse } from "../types";
import { Button } from "./Button";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import { Text } from "./Text";

function InvoiceRow({ item }: { item: PortalInvoiceHeader }) {
  const number = present(item.invoice_number);
  const fullType = present(item.full_type);
  const issued = formatInvoiceIssuedAt(item.issued_at);
  const amount = present(item.amount)
    ? formatMontoDisplay(item.amount)
    : "";
  const status = present(item.status);

  return (
    <View
      accessibilityLabel={`Factura ${number}${status ? `, ${status}` : ""}`}
      style={styles.row}
    >
      <Text variant="title" style={styles.number}>
        {number ? `Factura ${number}` : "Factura"}
      </Text>
      {fullType ? (
        <Text variant="meta" style={styles.meta}>
          {fullType}
        </Text>
      ) : null}
      {amount ? (
        <Text variant="body" style={styles.meta}>
          {amount}
        </Text>
      ) : null}
      {issued ? (
        <Text variant="meta" style={styles.meta}>
          {`Emitida: ${issued}`}
        </Text>
      ) : null}
      {status ? (
        <Text variant="meta" style={styles.meta}>
          {`Estado: ${status}`}
        </Text>
      ) : null}
    </View>
  );
}

export function InvoiceHeadersSection({
  loading,
  data,
  transportError,
  onRetry,
}: {
  loading: boolean;
  data: PortalInvoicesResponse | null;
  transportError: boolean;
  onRetry: () => void;
}) {
  const phase = invoiceUiPhase({
    loading,
    transportError,
    status: data?.status ?? null,
    count: data?.invoices.length ?? 0,
  });

  return (
    <View style={styles.wrap}>
      <SectionHeader title="Últimas facturas" />
      {phase === "loading" ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.brand} />
          <Text variant="meta">Cargando facturas…</Text>
        </View>
      ) : null}
      {phase === "unavailable" ? (
        <Card>
          <Text>No pudimos consultar tus facturas ahora.</Text>
          <Button
            label="Reintentar"
            variant="ghost"
            onPress={onRetry}
            accessibilityHint="Vuelve a consultar las facturas"
            style={styles.cta}
          />
        </Card>
      ) : null}
      {phase === "empty" ? (
        <Card>
          <Text>No encontramos facturas recientes en tu cuenta.</Text>
        </Card>
      ) : null}
      {phase === "success" && data ? (
        <Card>
          {data.invoices.map((item, index) => (
            <InvoiceRow
              key={`${item.invoice_number}-${item.issued_at ?? ""}-${index}`}
              item={item}
            />
          ))}
        </Card>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  loading: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 44,
  },
  row: {
    gap: spacing.xs,
    paddingBottom: spacing.sm,
    marginBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  number: { fontSize: 17 },
  meta: { marginTop: spacing.xs },
  cta: { marginTop: spacing.sm },
});

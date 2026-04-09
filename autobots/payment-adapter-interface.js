/**
 * Payment Adapter Interface
 *
 * Contract that any payment adapter must implement.
 * Canton uses optimistic billing (server creates ChargeReceipts),
 * so there's no client-side pay() — only authenticate + balance check.
 */

export class PaymentAdapter {
  /**
   * Authenticate with the MCP server using a Canton key file.
   * @param {string} keyFilePath - Path to Canton key JSON file
   * @param {string} serverUrl - MCP server base URL
   * @returns {{ token: string, partyId: string, fingerprint: string }}
   */
  async authenticate(keyFilePath, serverUrl) {
    throw new Error("Not implemented");
  }

  /**
   * Refresh authentication token if expired.
   * @param {string} serverUrl - MCP server base URL
   * @returns {{ token: string }}
   */
  async refreshToken(serverUrl) {
    throw new Error("Not implemented");
  }

  /**
   * Get current billing balance for the authenticated party.
   * @param {string} billingPortalUrl - Billing portal base URL
   * @returns {{ balance: number, totalCharged: number, totalCredited: number }}
   */
  async getBalance(billingPortalUrl) {
    throw new Error("Not implemented");
  }

  /** @returns {string} The authenticated party ID */
  get partyId() {
    throw new Error("Not implemented");
  }

  /** @returns {string} The current JWT token */
  get token() {
    throw new Error("Not implemented");
  }

  /** @returns {string} The party fingerprint */
  get fingerprint() {
    throw new Error("Not implemented");
  }
}

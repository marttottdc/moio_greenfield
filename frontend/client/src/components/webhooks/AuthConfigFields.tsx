import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Copy, RefreshCw } from "lucide-react";
import { generateToken, generateSecret, copyToClipboard } from "@/lib/webhookUtils";
import { useToast } from "@/hooks/use-toast";

export interface AuthConfig {
  token?: string;
  username?: string;
  password?: string;
  secret?: string;
  signature_header?: string;
  header?: string;
  value?: string;
  param?: string;
  jwt_secret?: string;
  algorithm?: string;
}

interface AuthConfigFieldsProps {
  authType: string;
  authConfig: AuthConfig;
  onChange: (config: AuthConfig) => void;
}

export function AuthConfigFields({
  authType,
  authConfig,
  onChange,
}: AuthConfigFieldsProps) {
  const { toast } = useToast();

  if (authType === "none") {
    return null;
  }

  const handleCopy = async (value: string | undefined, fieldName: string) => {
    if (!value) return;
    const success = await copyToClipboard(value);
    if (success) {
      toast({ title: `${fieldName} copied to clipboard` });
    }
  };

  const handleGenerate = (fieldName: keyof AuthConfig, isSecret: boolean = false) => {
    const newValue = isSecret ? generateSecret() : generateToken();
    onChange({ ...authConfig, [fieldName]: newValue });
  };

  if (authType === "bearer") {
    return (
      <div className="space-y-3 p-3 bg-muted/50 rounded-md">
        <h4 className="text-sm font-medium">Bearer Token Configuration</h4>
        <div className="space-y-2">
          <Label htmlFor="bearer-token">Bearer Token</Label>
          <div className="flex gap-2">
            <Input
              id="bearer-token"
              type="password"
              value={authConfig.token || ""}
              onChange={(e) => onChange({ ...authConfig, token: e.target.value })}
              placeholder="Enter or generate token"
              data-testid="input-bearer-token"
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleGenerate("token")}
              data-testid="button-generate-bearer"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleCopy(authConfig.token, "Token")}
              data-testid="button-copy-bearer"
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (authType === "basic") {
    return (
      <div className="space-y-3 p-3 bg-muted/50 rounded-md">
        <h4 className="text-sm font-medium">HTTP Basic Authentication</h4>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="basic-username">Username</Label>
            <Input
              id="basic-username"
              value={authConfig.username || ""}
              onChange={(e) => onChange({ ...authConfig, username: e.target.value })}
              placeholder="Username"
              data-testid="input-basic-username"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="basic-password">Password</Label>
            <Input
              id="basic-password"
              type="password"
              value={authConfig.password || ""}
              onChange={(e) => onChange({ ...authConfig, password: e.target.value })}
              placeholder="Password"
              data-testid="input-basic-password"
            />
          </div>
        </div>
      </div>
    );
  }

  if (authType === "hmac") {
    return (
      <div className="space-y-3 p-3 bg-muted/50 rounded-md">
        <h4 className="text-sm font-medium">HMAC-SHA256 Configuration</h4>
        <div className="space-y-2">
          <Label htmlFor="hmac-secret">Secret Key</Label>
          <div className="flex gap-2">
            <Input
              id="hmac-secret"
              type="password"
              value={authConfig.secret || ""}
              onChange={(e) => onChange({ ...authConfig, secret: e.target.value })}
              placeholder="HMAC secret"
              data-testid="input-hmac-secret"
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleGenerate("secret", true)}
              data-testid="button-generate-hmac"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleCopy(authConfig.secret, "Secret")}
              data-testid="button-copy-hmac"
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="hmac-header">Signature Header</Label>
          <Input
            id="hmac-header"
            value={authConfig.signature_header || "X-Signature"}
            onChange={(e) => onChange({ ...authConfig, signature_header: e.target.value })}
            placeholder="X-Signature"
            data-testid="input-hmac-header"
          />
        </div>
      </div>
    );
  }

  if (authType === "header") {
    return (
      <div className="space-y-3 p-3 bg-muted/50 rounded-md">
        <h4 className="text-sm font-medium">Custom Header Authentication</h4>
        <div className="space-y-2">
          <Label htmlFor="header-name">Header Name</Label>
          <Input
            id="header-name"
            value={authConfig.header || "X-Webhook-Key"}
            onChange={(e) => onChange({ ...authConfig, header: e.target.value })}
            placeholder="X-Webhook-Key"
            data-testid="input-header-name"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="header-value">Header Value</Label>
          <div className="flex gap-2">
            <Input
              id="header-value"
              type="password"
              value={authConfig.value || ""}
              onChange={(e) => onChange({ ...authConfig, value: e.target.value })}
              placeholder="Secret value"
              data-testid="input-header-value"
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleGenerate("value")}
              data-testid="button-generate-header"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (authType === "query") {
    return (
      <div className="space-y-3 p-3 bg-muted/50 rounded-md">
        <h4 className="text-sm font-medium">Query Parameter Authentication</h4>
        <div className="space-y-2">
          <Label htmlFor="query-param">Parameter Name</Label>
          <Input
            id="query-param"
            value={authConfig.param || "token"}
            onChange={(e) => onChange({ ...authConfig, param: e.target.value })}
            placeholder="token"
            data-testid="input-query-param"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="query-value">Parameter Value</Label>
          <div className="flex gap-2">
            <Input
              id="query-value"
              type="password"
              value={authConfig.value || ""}
              onChange={(e) => onChange({ ...authConfig, value: e.target.value })}
              placeholder="Secret value"
              data-testid="input-query-value"
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleGenerate("value")}
              data-testid="button-generate-query"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (authType === "jwt") {
    return (
      <div className="space-y-3 p-3 bg-muted/50 rounded-md">
        <h4 className="text-sm font-medium">JWT Token Configuration</h4>
        <div className="space-y-2">
          <Label htmlFor="jwt-secret">Secret Key</Label>
          <div className="flex gap-2">
            <Input
              id="jwt-secret"
              type="password"
              value={authConfig.jwt_secret || ""}
              onChange={(e) => onChange({ ...authConfig, jwt_secret: e.target.value })}
              placeholder="JWT secret"
              data-testid="input-jwt-secret"
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => handleGenerate("jwt_secret", true)}
              data-testid="button-generate-jwt"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="jwt-algorithm">Algorithm</Label>
          <Input
            id="jwt-algorithm"
            value={authConfig.algorithm || "HS256"}
            onChange={(e) => onChange({ ...authConfig, algorithm: e.target.value })}
            placeholder="HS256"
            data-testid="input-jwt-algorithm"
          />
        </div>
      </div>
    );
  }

  return null;
}

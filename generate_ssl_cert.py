#!/usr/bin/env python3

"""
SSL Certificate Generator for VaultHunters Web Manager

Generates self-signed SSL certificates for development and testing purposes.
For production use, replace with certificates from a trusted CA.
"""

import os
import subprocess
import sys
from pathlib import Path

def generate_self_signed_cert(cert_dir="certs", cert_name="server", days=365):
    """
    Generate a self-signed SSL certificate using OpenSSL
    
    Args:
        cert_dir (str): Directory to store certificates
        cert_name (str): Base name for certificate files  
        days (int): Certificate validity period in days
    
    Returns:
        tuple: (cert_path, key_path) or (None, None) if failed
    """
    
    # Create certificate directory
    cert_path_obj = Path(cert_dir)
    cert_path_obj.mkdir(exist_ok=True)
    
    cert_file = cert_path_obj / f"{cert_name}.crt"
    key_file = cert_path_obj / f"{cert_name}.key"
    
    # Check if OpenSSL is available
    try:
        subprocess.run(['openssl', 'version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: OpenSSL not found. Please install OpenSSL to generate certificates.")
        print("Ubuntu/Debian: sudo apt-get install openssl")
        print("RHEL/CentOS: sudo yum install openssl")
        print("Arch: sudo pacman -S openssl")
        return None, None
    
    # Generate certificate
    print(f"Generating self-signed SSL certificate...")
    print(f"Certificate: {cert_file}")
    print(f"Private key: {key_file}")
    print(f"Validity: {days} days")
    
    try:
        # Generate private key and certificate in one command
        cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
            '-keyout', str(key_file),
            '-out', str(cert_file),
            '-days', str(days),
            '-nodes',  # Don't encrypt private key
            '-subj', '/C=US/ST=State/L=City/O=VaultHunters/OU=WebManager/CN=localhost'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"ERROR: Failed to generate certificate: {result.stderr}")
            return None, None
        
        # Set appropriate permissions
        os.chmod(key_file, 0o600)  # Private key readable only by owner
        os.chmod(cert_file, 0o644)  # Certificate readable by all
        
        print("✅ SSL certificate generated successfully!")
        print(f"📄 Certificate: {cert_file}")
        print(f"🔐 Private key: {key_file}")
        print("")
        print("⚠️  WARNING: This is a self-signed certificate!")
        print("   Browsers will show security warnings.")
        print("   For production use, obtain certificates from a trusted CA.")
        
        return str(cert_file), str(key_file)
        
    except Exception as e:
        print(f"ERROR: Failed to generate certificate: {e}")
        return None, None

def main():
    """Main function"""
    print("VaultHunters Web Manager - SSL Certificate Generator")
    print("=" * 50)
    
    # Check if certificates already exist
    cert_dir = Path("certs")
    cert_file = cert_dir / "server.crt" 
    key_file = cert_dir / "server.key"
    
    if cert_file.exists() and key_file.exists():
        response = input(f"Certificates already exist in {cert_dir}/. Regenerate? (y/N): ").lower()
        if response != 'y':
            print("Certificate generation cancelled.")
            return
    
    # Generate certificate
    cert_path, key_path = generate_self_signed_cert()
    
    if cert_path and key_path:
        print("")
        print("Next steps:")
        print("1. Update your config.toml to enable SSL:")
        print("   [web]")
        print("   ssl_enabled = true")
        print("   ssl_cert_path = \"certs/server.crt\"") 
        print("   ssl_key_path = \"certs/server.key\"")
        print("")
        print("2. Restart the web manager")
        print("3. Access via https://localhost:8080")
    else:
        print("❌ Certificate generation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
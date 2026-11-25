package satchelservice

import (
	"bytes"
	"crypto/ed25519"

	"filippo.io/edwards25519"
)

var inverseEd25519Cofactor = func() *edwards25519.Scalar {
	encoded := [32]byte{8}
	cofactor, _ := new(edwards25519.Scalar).SetCanonicalBytes(encoded[:])
	return new(edwards25519.Scalar).Invert(cofactor)
}()

// ValidAuthorityPublicKey accepts only a canonically encoded, nonidentity
// Ed25519 key in the prime-order subgroup.
func ValidAuthorityPublicKey(key ed25519.PublicKey) bool {
	point, err := new(edwards25519.Point).SetBytes(key)
	if err != nil || !bytes.Equal(point.Bytes(), key) || point.Equal(edwards25519.NewIdentityPoint()) == 1 {
		return false
	}

	// Multiplication by 8 removes any torsion component. Dividing by 8
	// within the prime-order subgroup recovers the key only if it had none.
	cleared := new(edwards25519.Point).MultByCofactor(point)
	projected := new(edwards25519.Point).ScalarMult(inverseEd25519Cofactor, cleared)
	return projected.Equal(point) == 1
}

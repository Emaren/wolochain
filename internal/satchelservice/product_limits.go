package satchelservice

// Product ceilings from the owner's October 21 release mandate. They never
// enlarge an existing signed owner mandate, reviewer approval or configured
// signer limit: each narrower original authorization remains mandatory.
const (
	ProductMaxWagerWOLO     = 10_000
	ProductMaxAutoDailyWOLO = 50_000
	ProductMaxWagerUWolo    = ProductMaxWagerWOLO * 1_000_000
)
